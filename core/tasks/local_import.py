"""
ローカルファイル取り込みタスク
固定ディレクトリからファイルを走査し、メディアとして取り込む
"""

import os
import hashlib
import shutil
import json
import logging
import subprocess
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.utils import open_image_compat, register_heif_support

register_heif_support()

from PIL import Image
from PIL.ExifTags import TAGS
from flask import current_app

from core.db import db
from core.models.photo_models import (
    Media,
    Exif,
    PickerSelection,
    MediaItem,
    PhotoMetadata,
    VideoMetadata,
    MediaPlayback,
)
from core.models.job_sync import JobSync
from core.models.celery_task import CeleryTaskRecord, CeleryTaskStatus
from core.models.picker_session import PickerSession
from core.utils import get_file_date_from_name, get_file_date_from_exif
from core.logging_config import setup_task_logging, log_task_error, log_task_info
from core.tasks.media_post_processing import (
    enqueue_thumbs_generate,
    process_media_post_import,
)
from core.tasks.thumbs_generate import thumbs_generate as _thumbs_generate
from core.storage_paths import first_existing_storage_path, storage_path_candidates
from webapp.config import Config

# Re-export ``thumbs_generate`` so tests can monkeypatch the function without
# reaching into the deeper module.  The helper is still invoked via
# :func:`_regenerate_duplicate_video_thumbnails` but can be swapped out in
# environments where the heavy thumbnail pipeline is not available (for
# example in SQLite based test runs).
thumbs_generate = _thumbs_generate

# Setup logger for this module - use Celery task logger for consistency
logger = setup_task_logging(__name__)
# Also get celery task logger for cross-compatibility
celery_logger = logging.getLogger('celery.task.local_import')


_THUMBNAIL_RETRY_TASK_NAME = "thumbnail.retry"


class LocalImportPlaybackError(RuntimeError):
    """Raised when playback assets for a local video could not be prepared."""


def _is_recoverable_playback_failure(note: str) -> bool:
    """Return ``True`` when a playback failure can be safely downgraded.

    ``ffmpeg`` が利用できない (``ffmpeg_missing``) など、テスト環境や軽量な
    実行環境では発生し得る失敗は、メディア自体の取り込みを止める必要がない。
    そういったケースではセッションの進行を継続しつつ警告ログだけを残す。
    """

    if not note:
        return False

    normalized = note.lower()
    recoverable_notes = {
        "ffmpeg_missing",
        "playback_skipped",  # 互換性維持のためのエイリアス
    }

    if normalized in recoverable_notes:
        return True

    # ``ffmpeg`` 周りの一般的な失敗は ``ffmpeg_`` 接頭辞を含む
    if normalized.startswith("ffmpeg_"):
        return True

    return False


def _serialize_details(details: Dict[str, Any]) -> str:
    """詳細情報をJSON文字列へ変換。失敗時は文字列表現を返す。"""
    if not details:
        return ""

    try:
        return json.dumps(details, ensure_ascii=False, default=str)
    except TypeError:
        return str(details)


def _compose_message(
    message: str,
    details: Dict[str, Any],
    status: Optional[str] = None,
) -> str:
    """メッセージと詳細を結合してログに出力する文字列を生成。"""

    payload = details
    if status is not None:
        payload = dict(details)
        payload.setdefault("status", status)

    serialized = _serialize_details(payload)
    if not serialized:
        return message
    return f"{message} | details={serialized}"


def _with_session(details: Dict[str, Any], session_id: Optional[str]) -> Dict[str, Any]:
    """ログ詳細に session_id を追加した辞書を返す。"""

    merged = dict(details)
    if session_id is not None and "session_id" not in merged:
        merged["session_id"] = session_id
    return merged


def _file_log_context(file_path: Optional[str], filename: Optional[str] = None) -> Dict[str, Any]:
    """ファイル関連ログに共通のコンテキストを生成する。"""

    context: Dict[str, Any] = {}
    base_name = filename

    if not base_name and file_path:
        base_name = os.path.basename(file_path)

    display_value = file_path or base_name

    if display_value:
        context["file"] = display_value

    if file_path:
        context["file_path"] = file_path
        if base_name and base_name != file_path:
            context["basename"] = base_name
    elif base_name:
        context["basename"] = base_name

    return context


def _existing_media_destination_context(
    media: Media, originals_dir: Optional[str]
) -> Dict[str, Any]:
    """既存メディアの保存先情報をログ用に組み立てる。"""

    details: Dict[str, Any] = {}

    if media is None:
        return details

    relative_path = getattr(media, "local_rel_path", None)
    if relative_path:
        details["relative_path"] = relative_path

        base_dir = os.fspath(originals_dir) if originals_dir else None
        if base_dir:
            absolute_path = os.path.normpath(os.path.join(base_dir, relative_path))
        else:
            absolute_path = relative_path

        details["imported_path"] = absolute_path
        details["destination"] = absolute_path

    filename = getattr(media, "filename", None)
    if filename:
        details["imported_filename"] = filename

    return details


def _log_info(
    event: str,
    message: str,
    *,
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    **details: Any,
) -> None:
    """情報ログを記録。"""
    payload = _with_session(details, session_id)
    resolved_status = status if status is not None else "info"
    composed = _compose_message(message, payload, resolved_status)
    log_task_info(
        logger,
        composed,
        event=event,
        status=resolved_status,
        **payload,
    )
    celery_logger.info(
        composed,
        extra={"event": event, "status": resolved_status, **payload},
    )


def _log_warning(
    event: str,
    message: str,
    *,
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    **details: Any,
) -> None:
    """警告ログを記録。"""
    payload = _with_session(details, session_id)
    resolved_status = status if status is not None else "warning"
    composed = _compose_message(message, payload, resolved_status)
    logger.warning(
        composed,
        extra={"event": event, "status": resolved_status, **payload},
    )
    celery_logger.warning(
        composed,
        extra={"event": event, "status": resolved_status, **payload},
    )


def _log_error(
    event: str,
    message: str,
    *,
    exc_info: bool = False,
    session_id: Optional[str] = None,
    **details: Any,
) -> None:
    """エラーログを記録。"""
    status_value = details.pop("status", None)
    payload = _with_session(details, session_id)
    resolved_status = status_value if status_value is not None else "error"
    composed = _compose_message(message, payload, resolved_status)
    log_task_error(
        logger,
        composed,
        event=event,
        exc_info=exc_info,
        status=resolved_status,
        **payload,
    )
    celery_logger.error(
        composed,
        extra={"event": event, "status": resolved_status, **payload},
        exc_info=exc_info,
    )


def _commit_with_error_logging(
    event: str,
    message: str,
    *,
    session_id: Optional[str] = None,
    celery_task_id: Optional[str] = None,
    exc_info: bool = True,
    **details: Any,
) -> None:
    """db.session.commit() を実行し、失敗時には詳細ログを記録する。"""

    try:
        db.session.commit()
    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            # ロールバック自体が失敗しても続行（元例外を優先）
            pass

        _log_error(
            event,
            message,
            session_id=session_id,
            celery_task_id=celery_task_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
            exc_info=exc_info,
            **details,
        )
        raise


# サポートするファイル拡張子
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.heic', '.heif'}
SUPPORTED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.3gp', '.webm'}
SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS


_EXTRACTED_DIRECTORIES: List[Path] = []


def _zip_extraction_base_dir() -> Path:
    """ZIP展開用のベースディレクトリを返す。"""
    base_dir = Path(tempfile.gettempdir()) / "local_import_zip"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _register_extracted_directory(path: Path) -> None:
    """後でクリーンアップするため展開先ディレクトリを登録。"""
    _EXTRACTED_DIRECTORIES.append(path)


def _cleanup_extracted_directories() -> None:
    """ZIP展開で生成されたディレクトリを削除。"""
    while _EXTRACTED_DIRECTORIES:
        dir_path = _EXTRACTED_DIRECTORIES.pop()
        try:
            shutil.rmtree(dir_path)
        except FileNotFoundError:
            continue
        except Exception as e:
            _log_warning(
                "local_import.zip.cleanup_failed",
                "ZIP展開ディレクトリの削除に失敗",
                directory=str(dir_path),
                error_type=type(e).__name__,
                error_message=str(e),
            )


def _extract_zip_archive(zip_path: str, *, session_id: Optional[str] = None) -> List[str]:
    """ZIPファイルを展開し、サポート対象ファイルのパスを返す。"""
    extracted_files: List[str] = []
    archive_path = Path(zip_path)
    extraction_dir = _zip_extraction_base_dir() / f"{archive_path.stem}_{uuid.uuid4().hex}"
    extraction_dir.mkdir(parents=True, exist_ok=True)
    _register_extracted_directory(extraction_dir)

    should_remove_archive = False

    try:
        with zipfile.ZipFile(zip_path) as archive:
            should_remove_archive = True
            for member in archive.infolist():
                if member.is_dir():
                    continue

                member_path = Path(member.filename)
                if member_path.is_absolute() or any(part == ".." for part in member_path.parts):
                    _log_warning(
                        "local_import.zip.unsafe_member",
                        "ZIP内の危険なパスをスキップ",
                        zip_path=zip_path,
                        member=member.filename,
                        session_id=session_id,
                    )
                    continue

                if member_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue

                target_path = extraction_dir / member_path
                target_path.parent.mkdir(parents=True, exist_ok=True)

                with archive.open(member) as src, open(target_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)

                extracted_files.append(str(target_path))
                _log_info(
                    "local_import.zip.member_extracted",
                    "ZIP内のファイルを抽出",
                    session_id=session_id,
                    status="extracted",
                    zip_path=zip_path,
                    member=member.filename,
                    extracted_path=str(target_path),
                )

    except zipfile.BadZipFile as e:
        _log_error(
            "local_import.zip.invalid",
            "ZIPファイルの展開に失敗",
            zip_path=zip_path,
            error_type=type(e).__name__,
            error_message=str(e),
            session_id=session_id,
        )
    except Exception as e:
        _log_error(
            "local_import.zip.extract_failed",
            "ZIPファイル展開中にエラーが発生",
            zip_path=zip_path,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
            session_id=session_id,
        )
    else:
        if extracted_files:
            _log_info(
                "local_import.zip.extracted",
                "ZIPファイルを展開",
                zip_path=zip_path,
                extracted_count=len(extracted_files),
                extraction_dir=str(extraction_dir),
                session_id=session_id,
                status="extracted",
            )
        else:
            _log_warning(
                "local_import.zip.no_supported_files",
                "ZIPファイルに取り込み対象ファイルがありません",
                zip_path=zip_path,
                session_id=session_id,
                status="skipped",
            )

    if should_remove_archive:
        try:
            os.remove(zip_path)
            _log_info(
                "local_import.zip.removed",
                "ZIPファイルを削除",
                zip_path=zip_path,
                session_id=session_id,
                status="cleaned",
            )
        except OSError as e:
            _log_warning(
                "local_import.zip.remove_failed",
                "ZIPファイルの削除に失敗",
                zip_path=zip_path,
                error_type=type(e).__name__,
                error_message=str(e),
                session_id=session_id,
                status="warning",
            )

    return extracted_files


def calculate_file_hash(file_path: str) -> str:
    """ファイルのSHA-256ハッシュを計算"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_image_dimensions(file_path: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    """画像の幅、高さ、向きを取得"""
    try:
        with open_image_compat(file_path) as img:
            width, height = img.size

            # EXIF orientationを取得
            orientation = None
            exif_dict = {}

            getexif = getattr(img, "getexif", None)
            if callable(getexif):
                try:
                    exif = getexif()
                except Exception:
                    exif = None
                if exif:
                    exif_dict = dict(exif.items())

            if not exif_dict and hasattr(img, "_getexif"):
                try:
                    raw = img._getexif()
                    if raw:
                        exif_dict = raw
                except Exception:
                    exif_dict = {}

            if not exif_dict:
                exif_bytes = (getattr(img, "info", {}) or {}).get("exif")
                if isinstance(exif_bytes, (bytes, bytearray)) and hasattr(Image, "Exif"):
                    try:
                        exif_reader = Image.Exif()
                        exif_reader.load(exif_bytes)
                        exif_dict = dict(exif_reader.items())
                    except Exception:
                        exif_dict = {}

            for tag, value in exif_dict.items():
                if TAGS.get(tag) == 'Orientation':
                    orientation = value
                    break

            return width, height, orientation
    except Exception:
        return None, None, None


def extract_exif_data(file_path: str) -> Dict:
    """EXIFデータを抽出"""
    exif_data = {}
    try:
        with open_image_compat(file_path) as img:
            exif_dict = {}

            getexif = getattr(img, "getexif", None)
            if callable(getexif):
                try:
                    exif = getexif()
                except Exception:
                    exif = None
                if exif:
                    exif_dict = dict(exif.items())

            if not exif_dict and hasattr(img, '_getexif'):
                try:
                    raw = img._getexif()
                    if raw:
                        exif_dict = raw
                except Exception:
                    exif_dict = {}

            if not exif_dict:
                exif_bytes = (getattr(img, "info", {}) or {}).get("exif")
                if isinstance(exif_bytes, (bytes, bytearray)) and hasattr(Image, "Exif"):
                    try:
                        exif_reader = Image.Exif()
                        exif_reader.load(exif_bytes)
                        exif_dict = dict(exif_reader.items())
                    except Exception:
                        exif_dict = {}

            for tag_id, value in exif_dict.items():
                tag = TAGS.get(tag_id, tag_id)
                exif_data[tag] = value

    except Exception:
        pass

    return exif_data


def _parse_ffprobe_datetime(value: str) -> Optional[datetime]:
    """ffprobeが返す日時文字列をUTCのdatetimeへ変換する。"""

    if not value:
        return None

    raw = value.strip()
    if not raw:
        return None

    normalized = raw

    # 一部のQuickTimeタグでは "YYYY-MM-DD HH:MM:SS" の形式で返るため、ISO8601に寄せる。
    if "T" not in normalized and " " in normalized:
        normalized = normalized.replace(" ", "T", 1)

    normalized = normalized.replace("Z", "+00:00")

    # タイムゾーンが +0900 のようにコロン無しで返るケースに対応
    if len(normalized) > 5 and normalized[-5] in {"+", "-"} and normalized[-3] != ":":
        normalized = f"{normalized[:-2]}:{normalized[-2:]}"

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt


def extract_video_metadata(file_path: str) -> Dict:
    """動画ファイルからメタデータを抽出（ffprobeを使用）"""
    metadata: Dict[str, Any] = {}
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(file_path)
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            info = json.loads(proc.stdout)
            
            # ビデオストリーム情報を取得
            streams = info.get("streams", [])
            video_streams = [s for s in streams if s.get("codec_type") == "video"]
            if video_streams:
                v_stream = video_streams[0]
                # FPSを取得
                if "r_frame_rate" in v_stream:
                    fps_str = v_stream["r_frame_rate"]
                    if "/" in fps_str:
                        num, den = fps_str.split("/")
                        if den != "0":
                            metadata["fps"] = float(num) / float(den)
                    else:
                        metadata["fps"] = float(fps_str)

                # 幅・高さを取得
                metadata["width"] = v_stream.get("width")
                metadata["height"] = v_stream.get("height")

                # ストリームタグから作成日時を確認
                stream_tags = v_stream.get("tags") or {}
                for key in ("creation_time", "com.apple.quicktime.creationdate", "date"):
                    shot_at_candidate = stream_tags.get(key)
                    if shot_at_candidate:
                        parsed = _parse_ffprobe_datetime(str(shot_at_candidate))
                        if parsed:
                            metadata["shot_at"] = parsed
                            break

            # フォーマット情報から時間を取得
            format_info = info.get("format", {})
            if "duration" in format_info:
                metadata["duration_ms"] = int(float(format_info["duration"]) * 1000)

            # フォーマットタグに作成日時が含まれていれば利用
            format_tags = format_info.get("tags") or {}
            if "shot_at" not in metadata:
                for key in ("creation_time", "com.apple.quicktime.creationdate", "date"):
                    shot_at_candidate = format_tags.get(key)
                    if shot_at_candidate:
                        parsed = _parse_ffprobe_datetime(str(shot_at_candidate))
                        if parsed:
                            metadata["shot_at"] = parsed
                            break

    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError, ValueError):
        # ffprobeが使えない場合やエラーの場合は空のメタデータを返す
        pass

    return metadata


def generate_filename(shot_at: datetime, file_extension: str, file_hash: str) -> str:
    """
    ファイル名を生成
    フォーマット: YYYYMMDD_HHMMSS_local_hash8.ext
    """
    date_str = shot_at.strftime("%Y%m%d_%H%M%S")
    hash8 = file_hash[:8]
    return f"{date_str}_local_{hash8}{file_extension}"


def get_relative_path(shot_at: datetime, filename: str) -> str:
    """相対パスを生成 (YYYY/MM/DD/filename)"""
    year = shot_at.strftime("%Y")
    month = shot_at.strftime("%m")
    day = shot_at.strftime("%d")
    return f"{year}/{month}/{day}/{filename}"


def check_duplicate_media(file_hash: str, file_size: int) -> Optional[Media]:
    """重複チェック: SHA-256 + サイズ一致"""
    return Media.query.filter_by(
        hash_sha256=file_hash,
        bytes=file_size,
        is_deleted=False,
    ).first()


def _refresh_existing_media_metadata(
    media: Media,
    *,
    originals_dir: str,
    fallback_path: str,
    file_extension: str,
    session_id: Optional[str] = None,
) -> bool:
    """既存メディアのメタデータをローカルファイルから再適用する。"""

    candidate_paths = []
    if media.local_rel_path:
        original_path = os.path.join(originals_dir, media.local_rel_path)
        candidate_paths.append(original_path)
    candidate_paths.append(fallback_path)

    source_path = next((p for p in candidate_paths if p and os.path.exists(p)), None)
    if not source_path:
        _log_warning(
            "local_import.file.duplicate_source_missing",
            "メタデータ再適用用のソースファイルが見つかりません",
            media_id=media.id,
            originals_dir=originals_dir,
            fallback_path=fallback_path,
            session_id=session_id,
            status="missing",
        )
        return False

    file_size = os.path.getsize(source_path)
    file_hash = calculate_file_hash(source_path)

    is_video = file_extension in SUPPORTED_VIDEO_EXTENSIONS
    width, height, orientation = None, None, None
    duration_ms = None
    exif_data: Dict[str, Any] = {}
    video_metadata: Dict[str, Any] = {}

    if not is_video and file_extension in SUPPORTED_IMAGE_EXTENSIONS:
        width, height, orientation = get_image_dimensions(source_path)
        exif_data = extract_exif_data(source_path)
    elif is_video:
        video_metadata = extract_video_metadata(source_path)
        if video_metadata:
            width = video_metadata.get("width") or width
            height = video_metadata.get("height") or height
            duration_ms = video_metadata.get("duration_ms") or duration_ms

    shot_at = None
    if exif_data:
        shot_at = get_file_date_from_exif(exif_data)
    if not shot_at:
        shot_at = get_file_date_from_name(os.path.basename(source_path))
    if not shot_at:
        shot_at = datetime.fromtimestamp(os.path.getmtime(source_path), tz=timezone.utc)

    mime_type_map = {
        '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.png': 'image/png', '.tiff': 'image/tiff', '.tif': 'image/tiff',
        '.bmp': 'image/bmp', '.heic': 'image/heic', '.heif': 'image/heif',
        '.mp4': 'video/mp4', '.mov': 'video/quicktime',
        '.avi': 'video/x-msvideo', '.mkv': 'video/x-matroska',
        '.m4v': 'video/mp4', '.3gp': 'video/3gpp', '.webm': 'video/webm'
    }
    mime_type = mime_type_map.get(file_extension, 'application/octet-stream')

    media.mime_type = mime_type
    media.hash_sha256 = file_hash
    media.bytes = file_size
    if width is not None:
        media.width = width
    if height is not None:
        media.height = height
    if duration_ms is not None:
        media.duration_ms = duration_ms
    if orientation is not None:
        media.orientation = orientation
    if shot_at:
        media.shot_at = shot_at
    media.is_video = is_video

    if exif_data:
        media.camera_make = exif_data.get('Make') or media.camera_make
        media.camera_model = exif_data.get('Model') or media.camera_model

    media_item = None
    if media.google_media_id:
        media_item = MediaItem.query.get(media.google_media_id)
        if media_item:
            media_item.mime_type = mime_type
            media_item.filename = os.path.basename(media.filename or source_path)
            if width is not None:
                media_item.width = width
            if height is not None:
                media_item.height = height
            if exif_data:
                media_item.camera_make = exif_data.get('Make') or media_item.camera_make
                media_item.camera_model = exif_data.get('Model') or media_item.camera_model
            media_item.type = "VIDEO" if is_video else "PHOTO"

            if not is_video and exif_data:
                photo_meta = media_item.photo_metadata or PhotoMetadata()
                if 'FocalLength' in exif_data:
                    photo_meta.focal_length = exif_data.get('FocalLength')
                if 'FNumber' in exif_data:
                    photo_meta.aperture_f_number = exif_data.get('FNumber')
                if 'ISOSpeedRatings' in exif_data:
                    photo_meta.iso_equivalent = exif_data.get('ISOSpeedRatings')
                exposure_value = exif_data.get('ExposureTime') if 'ExposureTime' in exif_data else None
                photo_meta.exposure_time = str(exposure_value) if exposure_value not in (None, '') else None
                media_item.photo_metadata = photo_meta
                db.session.add(photo_meta)
                db.session.flush()
            elif is_video:
                video_meta = media_item.video_metadata or VideoMetadata(processing_status='UNSPECIFIED')
                if video_metadata:
                    if 'fps' in video_metadata:
                        video_meta.fps = video_metadata.get('fps')
                    if 'processing_status' in video_metadata:
                        video_meta.processing_status = video_metadata.get('processing_status')
                if video_meta.processing_status is None:
                    video_meta.processing_status = 'UNSPECIFIED'
                media_item.video_metadata = video_meta
                db.session.add(video_meta)
                db.session.flush()
    else:
        _log_warning(
            "local_import.file.duplicate_media_item_missing",
            "既存メディアに対応するMediaItemが見つかりません",
            media_id=media.id,
            media_google_id=media.google_media_id,
            session_id=session_id,
            status="warning",
        )

    if exif_data:
        exif = media.exif or Exif(media_id=media.id)
        exif.camera_make = exif_data.get('Make')
        exif.camera_model = exif_data.get('Model')
        exif.lens = exif_data.get('LensModel')
        exif.iso = exif_data.get('ISOSpeedRatings')
        shutter_value = exif_data.get('ExposureTime') if 'ExposureTime' in exif_data else None
        exif.shutter = str(shutter_value) if shutter_value not in (None, '') else None
        exif.f_number = exif_data.get('FNumber')
        exif.focal_len = exif_data.get('FocalLength')
        exif.gps_lat = exif_data.get('GPSLatitude')
        exif.gps_lng = exif_data.get('GPSLongitude')
        exif.raw_json = json.dumps(exif_data, ensure_ascii=False, default=str)
        db.session.add(exif)

    _commit_with_error_logging(
        "local_import.file.duplicate_refresh_commit",
        "重複メディアのメタデータを更新",
        session_id=session_id,
        media_id=media.id,
    )

    return True


def refresh_media_metadata_from_original(
    media: Media,
    *,
    originals_dir: str,
    fallback_path: str,
    file_extension: str,
    session_id: Optional[str] = None,
) -> bool:
    """Public wrapper for :func:`_refresh_existing_media_metadata`.

    The helper is reused outside of the local import task (for example from UI
    triggered recovery flows) while keeping the implementation centralised in a
    single location.
    """

    return _refresh_existing_media_metadata(
        media,
        originals_dir=originals_dir,
        fallback_path=fallback_path,
        file_extension=file_extension,
        session_id=session_id,
    )


def _regenerate_duplicate_video_thumbnails(
    media: Media,
    *,
    session_id: Optional[str] = None,
) -> None:
    """重複動画のサムネイル生成を再実行する。"""

    request_context = {"sessionId": session_id} if session_id else None

    thumb_func = thumbs_generate

    try:
        if thumb_func is None:
            result = enqueue_thumbs_generate(
                media.id,
                force=True,
                logger_override=logger,
                operation_id=f"duplicate-video-{media.id}",
                request_context=request_context,
            )
        else:
            result = thumb_func(media_id=media.id, force=True)
            _log_info(
                "local_import.duplicate_video.thumbnail_generate",
                "重複動画のサムネイル再生成を実行",
                session_id=session_id,
                media_id=media.id,
                status="thumbs_regen_started",
            )
    except Exception as exc:  # pragma: no cover - unexpected failure path
        _log_error(
            "local_import.duplicate_video.thumbnail_regen_failed",
            "重複動画のサムネイル再生成中に例外が発生",
            session_id=session_id,
            media_id=media.id,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return

    if result.get("ok"):
        paths = result.get("paths") or {}
        generated = result.get("generated", [])
        skipped = result.get("skipped", [])
        retry_scheduled = result.get("retry_scheduled", False)
        generated_paths = {
            size: paths[size]
            for size in generated
            if size in paths
        }
        skipped_paths = {
            size: paths[size]
            for size in skipped
            if size in paths
        }
        status = "thumbs_regenerated" if generated else "thumbs_skipped"
        _log_info(
            "local_import.duplicate_video.thumbnail_regenerated",
            "重複動画のサムネイルを再生成",
            session_id=session_id,
            media_id=media.id,
            generated=generated,
            skipped=skipped,
            notes=result.get("notes"),
            generated_paths=generated_paths,
            skipped_paths=skipped_paths,
            paths=paths,
            retry_scheduled=retry_scheduled,
            status=status,
        )
        if retry_scheduled:
            retry_details = result.get("retry_details") or {}
            _log_info(
                "local_import.duplicate_video.thumbnail_retry_scheduled",
                "重複動画のサムネイル再生成を後で再試行",
                session_id=session_id,
                media_id=media.id,
                retry_delay_seconds=retry_details.get("countdown"),
                celery_task_id=retry_details.get("celery_task_id"),
                notes=result.get("notes"),
                status="retry_scheduled",
            )
    else:
        _log_warning(
            "local_import.duplicate_video.thumbnail_regen_skipped",
            "重複動画のサムネイル再生成をスキップ",
            session_id=session_id,
            media_id=media.id,
            notes=result.get("notes"),
            retry_scheduled=result.get("retry_scheduled"),
            status="thumbs_skipped",
        )


def create_media_item_for_local(filename: str, mime_type: str, width: Optional[int], height: Optional[int],
                               is_video: bool, exif_data: Optional[Dict] = None, video_metadata: Optional[Dict] = None) -> MediaItem:
    """ローカルファイル用のMediaItemを作成"""
    import uuid
    
    # ファイル名からユニークなIDを生成
    media_item_id = f"local_{uuid.uuid4().hex[:16]}"
    
    # MediaItemタイプの決定
    item_type = "VIDEO" if is_video else "PHOTO"
    
    media_item = MediaItem(
        id=media_item_id,
        type=item_type,
        mime_type=mime_type,
        filename=filename,
        width=width,
        height=height,
        camera_make=exif_data.get('Make') if exif_data else None,
        camera_model=exif_data.get('Model') if exif_data else None
    )
    
    # メタデータの作成
    if is_video:
        # ビデオメタデータ（ffprobeから取得、取れない場合はNULL）
        video_meta = VideoMetadata(
            fps=video_metadata.get('fps') if video_metadata else None,
            processing_status='UNSPECIFIED'
        )
        db.session.add(video_meta)
        db.session.flush()  # IDを取得
        media_item.video_metadata_id = video_meta.id
    else:
        # フォトメタデータ（EXIFから取得、取れない場合はNULL）
        photo_meta = PhotoMetadata(
            focal_length=exif_data.get('FocalLength') if exif_data else None,
            aperture_f_number=exif_data.get('FNumber') if exif_data else None,
            iso_equivalent=exif_data.get('ISOSpeedRatings') if exif_data else None,
            exposure_time=str(exif_data.get('ExposureTime', '')) if exif_data and exif_data.get('ExposureTime') else None
        )
        db.session.add(photo_meta)
        db.session.flush()  # IDを取得
        media_item.photo_metadata_id = photo_meta.id
    
    db.session.add(media_item)
    return media_item


def import_single_file(
    file_path: str,
    import_dir: str,
    originals_dir: str,
    *,
    session_id: Optional[str] = None,
) -> Dict:
    """
    単一ファイルの取り込み処理
    
    Returns:
        処理結果辞書
    """
    result = {
        "success": False,
        "file_path": file_path,
        "reason": "",
        "media_id": None,
        "media_google_id": None,
        "metadata_refreshed": False,
    }

    file_context = _file_log_context(file_path)

    _log_info(
        "local_import.file.begin",
        "ローカルファイルの取り込みを開始",
        **file_context,
        import_dir=import_dir,
        originals_dir=originals_dir,
        session_id=session_id,
        status="processing",
    )

    try:
        # ファイル存在チェック
        if not os.path.exists(file_path):
            result["reason"] = "ファイルが存在しません"
            _log_warning(
                "local_import.file.missing",
                "取り込み対象ファイルが見つかりません",
                **file_context,
                session_id=session_id,
                status="missing",
            )
            return result

        # 拡張子チェック
        file_extension = Path(file_path).suffix.lower()
        if file_extension not in SUPPORTED_EXTENSIONS:
            result["reason"] = f"サポートされていない拡張子: {file_extension}"
            _log_warning(
                "local_import.file.unsupported",
                "サポート対象外拡張子のためスキップ",
                **file_context,
                extension=file_extension,
                session_id=session_id,
                status="unsupported",
            )
            return result

        # ファイルサイズとハッシュ計算
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            result["reason"] = "ファイルサイズが0です"
            _log_warning(
                "local_import.file.empty",
                "ファイルサイズが0のためスキップ",
                **file_context,
                session_id=session_id,
                status="skipped",
            )
            return result

        file_hash = calculate_file_hash(file_path)

        # 重複チェック
        existing_media = check_duplicate_media(file_hash, file_size)
        if existing_media:
            result["reason"] = f"重複ファイル (既存ID: {existing_media.id})"
            result["media_id"] = existing_media.id
            result["media_google_id"] = existing_media.google_media_id

            destination_details = _existing_media_destination_context(
                existing_media, originals_dir
            )
            for key in ("imported_path", "imported_filename", "relative_path"):
                value = destination_details.get(key)
                if value:
                    result[key] = value

            refreshed = False
            try:
                refreshed = _refresh_existing_media_metadata(
                    existing_media,
                    originals_dir=originals_dir,
                    fallback_path=file_path,
                    file_extension=file_extension,
                    session_id=session_id,
                )
            except Exception as refresh_exc:
                _log_error(
                    "local_import.file.duplicate_refresh_failed",
                    "重複ファイルのメタデータ更新中にエラーが発生",
                    **file_context,
                    media_id=existing_media.id,
                    **destination_details,
                    error_type=type(refresh_exc).__name__,
                    error_message=str(refresh_exc),
                    exc_info=True,
                    session_id=session_id,
                )
            else:
                if refreshed:
                    result["metadata_refreshed"] = True
                    result["reason"] = (
                        f"重複ファイル (既存ID: {existing_media.id}) - メタデータ更新"
                    )
                    _log_info(
                        "local_import.file.duplicate_refreshed",
                        "重複ファイルから既存メディアのメタデータを更新",
                        **file_context,
                        media_id=existing_media.id,
                        **destination_details,
                        session_id=session_id,
                        status="duplicate_refreshed",
                    )
                    try:
                        os.remove(file_path)
                        _log_info(
                            "local_import.file.duplicate_source_removed",
                            "重複ファイルのソースを削除",
                            **file_context,
                            media_id=existing_media.id,
                            **destination_details,
                            session_id=session_id,
                            status="cleaned",
                        )
                    except FileNotFoundError:
                        pass
                    except OSError as cleanup_exc:
                        _log_warning(
                            "local_import.file.duplicate_source_remove_failed",
                            "重複ファイル削除に失敗",
                            **file_context,
                            media_id=existing_media.id,
                            **destination_details,
                            error_type=type(cleanup_exc).__name__,
                            error_message=str(cleanup_exc),
                            session_id=session_id,
                            status="warning",
                        )
                else:
                    _log_info(
                        "local_import.file.duplicate",
                        "重複ファイルを検出したためスキップ",
                        **file_context,
                        media_id=existing_media.id,
                        **destination_details,
                        session_id=session_id,
                        status="duplicate",
                    )

            if existing_media.is_video:
                _regenerate_duplicate_video_thumbnails(
                    existing_media,
                    session_id=session_id,
                )

            return result

        is_video = file_extension in SUPPORTED_VIDEO_EXTENSIONS

        # 撮影日時とメタデータの取得
        shot_at = None
        exif_data: Optional[Dict[str, Any]] = None
        video_meta: Optional[Dict[str, Any]] = None

        if is_video:
            video_meta = extract_video_metadata(file_path)
            if video_meta:
                candidate = video_meta.get("shot_at")
                if isinstance(candidate, datetime):
                    shot_at = candidate
                elif isinstance(candidate, str):
                    shot_at = _parse_ffprobe_datetime(candidate)
        elif file_extension in SUPPORTED_IMAGE_EXTENSIONS:
            exif_data = extract_exif_data(file_path)
            shot_at = get_file_date_from_exif(exif_data)

        # EXIF/動画メタデータから取得できない場合は、ファイル名から取得
        if not shot_at:
            shot_at = get_file_date_from_name(os.path.basename(file_path))

        # それでも取得できない場合は、ファイルの更新日時を使用
        if not shot_at:
            mtime = os.path.getmtime(file_path)
            shot_at = datetime.fromtimestamp(mtime, tz=timezone.utc)
        
        # ファイル名とパスの生成
        new_filename = generate_filename(shot_at, file_extension, file_hash)
        rel_path = get_relative_path(shot_at, new_filename)
        dest_path = os.path.join(originals_dir, rel_path)
        imported_filename = new_filename
        
        # ディレクトリ作成
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        
        # メディア情報の取得
        width, height, orientation = None, None, None
        duration_ms = None

        if not is_video:
            width, height, orientation = get_image_dimensions(file_path)
        else:
            # 動画の場合はffprobeで取得済みのメタデータから値を利用
            if video_meta:
                width = video_meta.get('width') or width
                height = video_meta.get('height') or height
                duration_ms = video_meta.get('duration_ms') or duration_ms

        # MIMEタイプの決定
        mime_type_map = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.tiff': 'image/tiff', '.tif': 'image/tiff',
            '.bmp': 'image/bmp', '.heic': 'image/heic', '.heif': 'image/heif',
            '.mp4': 'video/mp4', '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo', '.mkv': 'video/x-matroska',
            '.m4v': 'video/mp4', '.3gp': 'video/3gpp', '.webm': 'video/webm'
        }
        mime_type = mime_type_map.get(file_extension, 'application/octet-stream')
        
        # ファイルコピー
        shutil.copy2(file_path, dest_path)
        _log_info(
            "local_import.file.copied",
            "ファイルを保存先にコピーしました",
            **file_context,
            destination=dest_path,
            imported_path=dest_path,
            imported_filename=imported_filename,
            session_id=session_id,
            status="copied",
        )
        
        # MediaItemとメタデータの作成
        media_item = create_media_item_for_local(
            filename=os.path.basename(file_path),
            mime_type=mime_type,
            width=width,
            height=height,
            is_video=is_video,
            exif_data=exif_data,
            video_metadata=video_meta
        )
        
        # DBへの登録
        media = Media(
            google_media_id=media_item.id,  # ローカルファイルの場合はmedia_item.idを使用
            account_id=None,                # ローカルファイルの場合はNone
            local_rel_path=rel_path,
            filename=os.path.basename(file_path),
            hash_sha256=file_hash,
            bytes=file_size,
            mime_type=mime_type,
            width=width,
            height=height,
            duration_ms=duration_ms,
            shot_at=shot_at,
            imported_at=datetime.now(timezone.utc),
            orientation=orientation,
            is_video=is_video,
            live_group_id=None,
            is_deleted=False,
            has_playback=False
        )
        
        db.session.add(media)
        db.session.flush()  # IDを取得

        # EXIFデータの保存（画像の場合、すでに取得済みのデータを使用）
        if not is_video and file_extension in SUPPORTED_IMAGE_EXTENSIONS and exif_data:
            exif = Exif(
                media_id=media.id,
                camera_make=exif_data.get('Make'),
                camera_model=exif_data.get('Model'),
                lens=exif_data.get('LensModel'),
                iso=exif_data.get('ISOSpeedRatings'),
                shutter=str(exif_data.get('ExposureTime', '')),
                f_number=exif_data.get('FNumber'),
                focal_len=exif_data.get('FocalLength'),
                gps_lat=exif_data.get('GPSLatitude'),
                gps_lng=exif_data.get('GPSLongitude'),
                raw_json=str(exif_data) if exif_data else None
            )
            db.session.add(exif)
        
        db.session.commit()

        post_process_result = process_media_post_import(
            media,
            logger_override=logger,
            request_context={
                "session_id": session_id,
                "source": "local_import",
            },
        )

        if post_process_result is not None:
            result["post_process"] = post_process_result

        if is_video:
            playback_result = (post_process_result or {}).get("playback") or {}
            if not playback_result.get("ok"):
                note = playback_result.get("note") or "unknown"
                if session_id and _is_recoverable_playback_failure(note):
                    _log_warning(
                        "local_import.file.playback_skipped",
                        "動画の再生ファイル生成をスキップ",
                        **file_context,
                        media_id=media.id,
                        note=note,
                        session_id=session_id,
                        status="warning",
                    )
                    result.setdefault("warnings", []).append(
                        f"playback_skipped:{note}"
                    )
                else:
                    raise LocalImportPlaybackError(
                        f"動画の再生ファイル生成に失敗しました (理由: {note})"
                    )
            else:
                db.session.refresh(media)
                if not media.has_playback:
                    raise LocalImportPlaybackError(
                        "動画の再生ファイル生成に失敗しました (理由: playback_not_marked)"
                    )

                playback_entry = MediaPlayback.query.filter_by(
                    media_id=media.id, preset="std1080p"
                ).first()
                if not playback_entry or not playback_entry.rel_path:
                    raise LocalImportPlaybackError(
                        "動画の再生ファイル生成に失敗しました (理由: playback_record_missing)"
                    )

                play_dir = _resolve_directory("FPV_NAS_PLAY_DIR")
                playback_path = os.path.join(play_dir, playback_entry.rel_path)
                if not os.path.exists(playback_path):
                    raise LocalImportPlaybackError(
                        "動画の再生ファイル生成に失敗しました (理由: playback_file_missing)"
                    )

        # 元ファイルの削除
        os.remove(file_path)
        _log_info(
            "local_import.file.source_removed",
            "取り込み完了後に元ファイルを削除",
            **file_context,
            session_id=session_id,
            status="cleaned",
        )

        result["success"] = True
        result["media_id"] = media.id
        result["media_google_id"] = media.google_media_id
        result["reason"] = "取り込み成功"
        result["imported_filename"] = imported_filename
        result["imported_path"] = dest_path

        _log_info(
            "local_import.file.success",
            "ローカルファイルの取り込みが完了",
            **file_context,
            media_id=media.id,
            relative_path=rel_path,
            imported_path=dest_path,
            imported_filename=imported_filename,
            session_id=session_id,
            status="success",
        )

    except Exception as e:
        db.session.rollback()
        _log_error(
            "local_import.file.failed",
            "ローカルファイル取り込み中にエラーが発生",
            **file_context,
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
            session_id=session_id,
            status="failed",
        )
        result["reason"] = f"エラー: {str(e)}"

        # コピー先ファイルが作成されていた場合は削除
        try:
            if 'dest_path' in locals() and os.path.exists(dest_path):
                os.remove(dest_path)
                _log_info(
                    "local_import.file.cleanup",
                    "エラー発生時にコピー済みファイルを削除",
                    destination=dest_path,
                    session_id=session_id,
                    status="cleaned",
                )
        except Exception as cleanup_error:
            _log_warning(
                "local_import.file.cleanup_failed",
                "エラー発生時のコピー済みファイル削除に失敗",
                destination=dest_path if 'dest_path' in locals() else None,
                error_type=type(cleanup_error).__name__,
                error_message=str(cleanup_error),
                session_id=session_id,
                status="warning",
            )

    return result


def scan_import_directory(import_dir: str, *, session_id: Optional[str] = None) -> List[str]:
    """取り込みディレクトリをスキャンしてサポートファイルを取得"""
    files = []
    
    if not os.path.exists(import_dir):
        return files
    
    for root, dirs, filenames in os.walk(import_dir):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            file_extension = Path(filename).suffix.lower()
            file_context = _file_log_context(file_path, filename)

            if file_extension in SUPPORTED_EXTENSIONS:
                files.append(file_path)
                _log_info(
                    "local_import.scan.file_added",
                    "取り込み対象ファイルを検出",
                    session_id=session_id,
                    status="scanning",
                    **file_context,
                    extension=file_extension,
                )
            elif file_extension == ".zip":
                _log_info(
                    "local_import.scan.zip_detected",
                    "ZIPファイルを検出",
                    session_id=session_id,
                    status="processing",
                    zip_path=file_path,
                )
                extracted = _extract_zip_archive(file_path, session_id=session_id)
                files.extend(extracted)
            else:
                _log_info(
                    "local_import.scan.unsupported",
                    "サポート対象外のファイルをスキップ",
                    session_id=session_id,
                    status="skipped",
                    **file_context,
                    extension=file_extension,
                )

    return files


def _resolve_directory(config_key: str) -> str:
    """Return a usable directory path for the given storage *config_key*."""

    path = first_existing_storage_path(config_key)
    if path:
        return path

    candidates = storage_path_candidates(config_key)
    if candidates:
        return candidates[0]

    raise RuntimeError(f"No storage directory candidates available for {config_key}")


def _set_session_progress(
    session: Optional[PickerSession],
    *,
    status: Optional[str] = None,
    stage: Optional[str] = None,
    celery_task_id: Optional[str] = None,
    stats_updates: Optional[Dict[str, Any]] = None,
) -> None:
    """Update session status/stats during local import processing."""

    if not session:
        return

    now = datetime.now(timezone.utc)
    if status:
        session.status = status
    session.last_progress_at = now
    session.updated_at = now

    stats = session.stats() if hasattr(session, "stats") else {}
    if not isinstance(stats, dict):
        stats = {}
    if stage is not None:
        stats["stage"] = stage
    if celery_task_id is not None:
        stats["celery_task_id"] = celery_task_id
    if stats_updates:
        stats.update(stats_updates)
    session.set_stats(stats)

    try:
        db.session.commit()
    except Exception as exc:  # pragma: no cover - exercised via integration tests
        db.session.rollback()
        _log_error(
            "local_import.session.progress_update_failed",
            "セッション状態の更新中にエラーが発生",
            session_id=session.session_id if hasattr(session, "session_id") else None,
            session_db_id=getattr(session, "id", None),
            error_type=type(exc).__name__,
            error_message=str(exc),
            exc_info=True,
        )
        raise


def _session_cancel_requested(
    session: Optional[PickerSession],
    *,
    task_instance=None,
) -> bool:
    """Return True when cancellation has been requested for *session*."""

    if not session:
        return False

    if task_instance and hasattr(task_instance, "is_aborted"):
        try:
            if task_instance.is_aborted():
                return True
        except Exception:
            pass

    try:
        db.session.refresh(session)
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        fresh = PickerSession.query.get(session.id)
        if not fresh:
            return True
        session.status = fresh.status
        session.stats_json = fresh.stats_json

    stats = session.stats() if hasattr(session, "stats") else {}
    if isinstance(stats, dict) and stats.get("cancel_requested"):
        return True

    return session.status == "canceled"


def _record_thumbnail_result(
    aggregate: Dict[str, Any],
    *,
    media_id: Optional[int],
    thumb_result: Dict[str, Any],
) -> None:
    """Collect thumbnail generation metadata for later aggregation."""

    if media_id is None or not isinstance(thumb_result, dict):
        return

    records = aggregate.setdefault("thumbnail_records", [])
    entry: Dict[str, Any] = {
        "mediaId": media_id,
        "media_id": media_id,
        "ok": thumb_result.get("ok"),
        "notes": thumb_result.get("notes"),
        "generated": thumb_result.get("generated"),
        "skipped": thumb_result.get("skipped"),
        "retry_scheduled": bool(thumb_result.get("retry_scheduled")),
    }

    retry_details = thumb_result.get("retry_details")
    if isinstance(retry_details, dict):
        entry["retry_details"] = retry_details

    ok_flag = thumb_result.get("ok")
    if ok_flag is False:
        entry["status"] = "error"
    elif entry["retry_scheduled"]:
        entry["status"] = "progress"
    else:
        entry["status"] = "completed"

    records.append(entry)


def build_thumbnail_task_snapshot(
    session: Optional[PickerSession],
    recorded_entries: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Summarise thumbnail generation state for *session*."""

    summary: Dict[str, Any] = {
        "total": 0,
        "completed": 0,
        "pending": 0,
        "failed": 0,
        "entries": [],
        "status": "idle",
    }

    if session is None or session.id is None:
        return summary

    initial: Dict[int, Dict[str, Any]] = {}
    if recorded_entries:
        for entry in recorded_entries:
            if not isinstance(entry, dict):
                continue
            media_id = entry.get("mediaId") or entry.get("media_id")
            if media_id is None:
                continue
            try:
                media_key = int(media_id)
            except (TypeError, ValueError):
                continue
            initial[media_key] = {
                "status": (entry.get("status") or "").lower() or None,
                "ok": entry.get("ok"),
                "notes": entry.get("notes"),
                "retry_scheduled": bool(
                    entry.get("retryScheduled") or entry.get("retry_scheduled")
                ),
                "retry_details": entry.get("retryDetails") or entry.get("retry_details"),
            }

    selection_rows = (
        db.session.query(
            PickerSelection.id,
            PickerSelection.status,
            Media.id.label("media_id"),
            Media.thumbnail_rel_path,
            Media.is_video,
        )
        .outerjoin(MediaItem, PickerSelection.google_media_id == MediaItem.id)
        .outerjoin(Media, Media.google_media_id == MediaItem.id)
        .filter(
            PickerSelection.session_id == session.id,
            PickerSelection.status == "imported",
        )
        .all()
    )

    if not selection_rows:
        return summary

    media_ids = [row.media_id for row in selection_rows if row.media_id is not None]
    celery_records: Dict[int, CeleryTaskRecord] = {}

    if media_ids:
        str_ids = [str(mid) for mid in media_ids]
        records = (
            CeleryTaskRecord.query.filter(
                CeleryTaskRecord.task_name == _THUMBNAIL_RETRY_TASK_NAME,
                CeleryTaskRecord.object_type == "media",
                CeleryTaskRecord.object_id.in_(str_ids),
            )
            .order_by(CeleryTaskRecord.id.desc())
            .all()
        )
        for record in records:
            try:
                mid = int(record.object_id) if record.object_id is not None else None
            except (TypeError, ValueError):
                continue
            if mid is None or mid in celery_records:
                continue
            celery_records[mid] = record

    summary["status"] = "progress"

    for row in selection_rows:
        media_id = row.media_id
        if media_id is None:
            continue

        summary["total"] += 1

        recorded = initial.get(media_id, {})
        base_status = (recorded.get("status") or "").lower() or None
        if recorded.get("ok") is False:
            base_status = "error"
        retry_flag = bool(recorded.get("retry_scheduled"))
        note = recorded.get("notes")
        retry_details = recorded.get("retry_details") if recorded else None

        record = celery_records.get(media_id)

        if row.thumbnail_rel_path:
            final_status = "completed"
            retry_flag = False
        else:
            if record is not None:
                if record.status in {
                    CeleryTaskStatus.SCHEDULED,
                    CeleryTaskStatus.QUEUED,
                    CeleryTaskStatus.RUNNING,
                }:
                    final_status = "progress"
                    retry_flag = True
                elif record.status == CeleryTaskStatus.SUCCESS:
                    final_status = "completed"
                    retry_flag = False
                elif record.status in {
                    CeleryTaskStatus.FAILED,
                    CeleryTaskStatus.CANCELED,
                }:
                    final_status = "error"
                else:
                    final_status = base_status or "progress"
            else:
                if base_status == "error":
                    final_status = "error"
                elif retry_flag or base_status in {"progress", "pending", "processing"}:
                    final_status = "progress"
                elif base_status == "completed":
                    final_status = "completed"
                else:
                    final_status = "progress"

        if final_status == "error":
            summary["failed"] += 1
        elif final_status == "completed":
            summary["completed"] += 1
        else:
            summary["pending"] += 1

        entry_payload: Dict[str, Any] = {
            "mediaId": media_id,
            "selectionId": row.id,
            "status": final_status,
            "retryScheduled": retry_flag,
            "thumbnailPath": row.thumbnail_rel_path,
            "notes": note,
            "isVideo": bool(row.is_video),
        }
        if isinstance(retry_details, dict):
            entry_payload["retryDetails"] = retry_details
        if record is not None:
            entry_payload["celeryTaskStatus"] = record.status.value

        summary["entries"].append(entry_payload)

    if summary["failed"] > 0:
        summary["status"] = "error"
    elif summary["pending"] > 0:
        summary["status"] = "progress"
    else:
        summary["status"] = "completed" if summary["total"] > 0 else "idle"

    return summary


def _enqueue_local_import_selections(
    session: Optional[PickerSession],
    file_paths: List[str],
    *,
    active_session_id: Optional[str],
    celery_task_id: Optional[str],
) -> int:
    """Ensure :class:`PickerSelection` rows exist for *file_paths* and mark them enqueued."""

    if not session or not file_paths:
        return 0

    now = datetime.now(timezone.utc)
    existing: Dict[str, PickerSelection] = {}
    selections = (
        PickerSelection.query.filter(
            PickerSelection.session_id == session.id,
            PickerSelection.local_file_path.in_(file_paths),
        ).all()
    )
    for sel in selections:
        if sel.local_file_path:
            existing[sel.local_file_path] = sel

    enqueued = 0
    for file_path in file_paths:
        filename = os.path.basename(file_path)
        file_context = _file_log_context(file_path, filename)
        selection = existing.get(file_path)
        if selection is None:
            selection = PickerSelection(
                session_id=session.id,
                google_media_id=None,
                local_file_path=file_path,
                local_filename=filename,
                status="enqueued",
                attempts=0,
                enqueued_at=now,
            )
            db.session.add(selection)
            db.session.flush()
            enqueued += 1
            _log_info(
                "local_import.selection.created",
                "取り込み対象ファイルのSelectionを作成",
                session_db_id=session.id,
                **file_context,
                selection_id=selection.id,
                session_id=active_session_id,
                celery_task_id=celery_task_id,
            )
        else:
            if selection.status in ("imported", "dup"):
                continue
            selection.status = "enqueued"
            selection.enqueued_at = now
            selection.local_filename = filename
            selection.local_file_path = file_path
            enqueued += 1
            _log_info(
                "local_import.selection.requeued",
                "既存Selectionを再キュー",
                session_db_id=session.id,
                **file_context,
                selection_id=selection.id,
                session_id=active_session_id,
                celery_task_id=celery_task_id,
            )

    _commit_with_error_logging(
        "local_import.selection.commit_failed",
        "Selectionの状態保存に失敗",
        session_id=active_session_id,
        celery_task_id=celery_task_id,
        session_db_id=getattr(session, "id", None),
        enqueued=enqueued,
    )
    return enqueued


def _pending_selections_query(session: PickerSession):
    pending_statuses = ("pending", "enqueued", "running")
    return (
        PickerSelection.query.filter(
            PickerSelection.session_id == session.id,
            PickerSelection.status.in_(pending_statuses),
        )
        .order_by(PickerSelection.id)
    )


def _process_local_import_queue(
    session: Optional[PickerSession],
    *,
    import_dir: str,
    originals_dir: str,
    result: Dict[str, Any],
    active_session_id: Optional[str],
    celery_task_id: Optional[str],
    task_instance=None,
) -> int:
    """Process pending selections for the session and import media files."""

    if not session:
        return 0

    selections = list(_pending_selections_query(session).all())
    total_files = len(selections)

    if _session_cancel_requested(session, task_instance=task_instance):
        _log_info(
            "local_import.cancel.detected",
            "キャンセル要求を検知したため処理を中断",
            session_id=active_session_id,
            celery_task_id=celery_task_id,
        )
        result["canceled"] = True
        return 0

    if task_instance and total_files:
        task_instance.update_state(
            state="PROGRESS",
            meta={
                "status": f"{total_files}個のファイルの取り込みを開始します",
                "progress": 0,
                "current": 0,
                "total": total_files,
                "message": "取り込み開始",
            },
        )

    canceled = False

    for index, selection in enumerate(selections, 1):
        file_path = selection.local_file_path
        filename = selection.local_filename or (os.path.basename(file_path) if file_path else f"selection_{selection.id}")
        file_context = _file_log_context(file_path, filename)
        display_file = file_context.get("file") or filename

        if _session_cancel_requested(session, task_instance=task_instance):
            _log_info(
                "local_import.cancel.pending_break",
                "キャンセル要求のため残りの処理をスキップ",
                session_id=active_session_id,
                celery_task_id=celery_task_id,
                processed=index - 1,
                remaining=total_files - (index - 1),
            )
            canceled = True
            if task_instance and total_files:
                task_instance.update_state(
                    state="PROGRESS",
                    meta={
                        "status": "キャンセル要求を受信しました",
                        "progress": int(((index - 1) / total_files) * 100) if total_files else 0,
                        "current": index - 1,
                        "total": total_files,
                        "message": "キャンセル処理中",
                    },
                )
            break

        result["processed"] += 1

        try:
            selection.status = "running"
            selection.started_at = datetime.now(timezone.utc)
            selection.error = None
            db.session.commit()
            _log_info(
                "local_import.selection.running",
                "Selectionを処理中に更新",
                selection_id=selection.id,
                **file_context,
                session_id=active_session_id,
                celery_task_id=celery_task_id,
            )
        except Exception as exc:
            db.session.rollback()
            _log_error(
                "local_import.selection.running_update_failed",
                "Selectionを処理中に更新できませんでした",
                selection_id=getattr(selection, "id", None),
                **file_context,
                error_type=type(exc).__name__,
                error_message=str(exc),
                session_id=active_session_id,
                celery_task_id=celery_task_id,
            )

        file_result = import_single_file(
            file_path or "",
            import_dir,
            originals_dir,
            session_id=active_session_id,
        )

        detail = {
            "file": display_file,
            "status": "success" if file_result["success"] else "failed",
            "reason": file_result["reason"],
            "media_id": file_result.get("media_id"),
        }
        basename = file_context.get("basename")
        if basename and basename != detail["file"]:
            detail["basename"] = basename
        result["details"].append(detail)

        post_process_result = file_result.get("post_process")
        if isinstance(post_process_result, dict):
            thumb_result = post_process_result.get("thumbnails")
            if isinstance(thumb_result, dict):
                thumb_detail: Dict[str, Any] = {
                    "ok": thumb_result.get("ok"),
                    "status": "error"
                    if thumb_result.get("ok") is False
                    else (
                        "progress"
                        if thumb_result.get("retry_scheduled")
                        else "completed"
                    ),
                    "generated": thumb_result.get("generated"),
                    "skipped": thumb_result.get("skipped"),
                    "retryScheduled": bool(thumb_result.get("retry_scheduled")),
                    "notes": thumb_result.get("notes"),
                }
                retry_details = thumb_result.get("retry_details")
                if isinstance(retry_details, dict):
                    thumb_detail["retryDetails"] = retry_details
                detail["thumbnail"] = thumb_detail
                _record_thumbnail_result(
                    result,
                    media_id=file_result.get("media_id"),
                    thumb_result=thumb_result,
                )

        try:
            media_google_id = file_result.get("media_google_id")
            if media_google_id:
                selection.google_media_id = media_google_id

            if file_result["success"]:
                selection.status = "imported"
                selection.finished_at = datetime.now(timezone.utc)
                result["success"] += 1
                _log_info(
                    "local_import.file.processed_success",
                    "ファイルの取り込みに成功",
                    **file_context,
                    media_id=file_result.get("media_id"),
                    session_id=active_session_id,
                    celery_task_id=celery_task_id,
                )
            else:
                reason = file_result["reason"]
                if "重複ファイル" in reason:
                    selection.status = "dup"
                    selection.finished_at = datetime.now(timezone.utc)
                    result["skipped"] += 1
                    detail["status"] = "skipped"
                    try:
                        if file_path and os.path.exists(file_path):
                            os.remove(file_path)
                            _log_info(
                                "local_import.file.duplicate_cleanup",
                                "重複ファイルの元ファイルを削除",
                                **file_context,
                                session_id=active_session_id,
                                celery_task_id=celery_task_id,
                            )
                    except Exception:
                        _log_warning(
                            "local_import.file.duplicate_cleanup_failed",
                            "重複ファイルの削除に失敗",
                            **file_context,
                            session_id=active_session_id,
                            celery_task_id=celery_task_id,
                        )
                else:
                    selection.status = "failed"
                    selection.error = reason
                    selection.finished_at = datetime.now(timezone.utc)
                    selection.attempts = (selection.attempts or 0) + 1
                    result["failed"] += 1
                    result["errors"].append(f"{display_file}: {reason}")
                    _log_warning(
                        "local_import.file.processed_failed",
                        "ファイルの取り込みに失敗",
                        **file_context,
                        reason=reason,
                        session_id=active_session_id,
                        celery_task_id=celery_task_id,
                    )

            db.session.commit()
            _log_info(
                "local_import.selection.updated",
                "Selectionの状態を更新",
                selection_id=selection.id,
                **file_context,
                status=selection.status,
                session_id=active_session_id,
                celery_task_id=celery_task_id,
            )
        except Exception as e:
            db.session.rollback()
            _log_error(
                "local_import.selection.update_failed",
                "Selectionの状態更新に失敗",
                **file_context,
                selection_id=getattr(selection, "id", None),
                error_type=type(e).__name__,
                error_message=str(e),
                session_id=active_session_id,
                celery_task_id=celery_task_id,
            )

        if task_instance and total_files:
            progress = int((index / total_files) * 100)
            task_instance.update_state(
                state="PROGRESS",
                meta={
                    "status": f"ファイル処理中: {display_file}",
                    "progress": progress,
                    "current": index,
                    "total": total_files,
                    "message": f"{index}/{total_files} 処理中",
                },
            )

    if canceled:
        result["canceled"] = True

    if task_instance and total_files and not canceled:
        task_instance.update_state(
            state="PROGRESS",
            meta={
                "status": "取り込み完了",
                "progress": 100,
                "current": total_files,
                "total": total_files,
                "message": f"完了: 成功{result['success']}, スキップ{result['skipped']}, 失敗{result['failed']}",
            },
        )

    return total_files


def local_import_task(task_instance=None, session_id=None) -> Dict:
    """
    ローカル取り込みタスクのメイン処理
    
    Args:
        task_instance: Celeryタスクインスタンス（進行状況報告用）
        session_id: API側で作成されたPickerSessionのID
    
    Returns:
        処理結果辞書
    """
    # Flaskアプリケーションのコンテキストから設定を取得
    try:
        import_dir = _resolve_directory('LOCAL_IMPORT_DIR')
    except RuntimeError:
        import_dir = Config.LOCAL_IMPORT_DIR

    try:
        originals_dir = _resolve_directory('FPV_NAS_ORIGINALS_DIR')
    except RuntimeError:
        originals_dir = Config.FPV_NAS_ORIGINALS_DIR

    celery_task_id = None
    if task_instance is not None:
        request = getattr(task_instance, "request", None)
        celery_task_id = getattr(request, "id", None)

    result = {
        "ok": True,
        "processed": 0,
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "details": [],
        "session_id": session_id,
        "celery_task_id": celery_task_id,
        "canceled": False,
    }

    # API側で作成されたセッションを取得
    session = None
    if session_id:
        try:
            session = PickerSession.query.filter_by(session_id=session_id).first()
            if not session:
                _log_error(
                    "local_import.session.missing",
                    "指定されたセッションIDのレコードが見つかりません",
                    session_id=session_id,
                )
                result["errors"].append(f"セッションが見つかりません: {session_id}")
                return result
            _log_info(
                "local_import.session.attach",
                "既存セッションをローカルインポートに紐付け",
                session_id=session_id,
                celery_task_id=celery_task_id,
                status="attached",
            )
        except Exception as e:
            _log_error(
                "local_import.session.load_failed",
                "セッション取得時にエラーが発生",
                session_id=session_id,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            result["errors"].append(f"セッション取得エラー: {str(e)}")
            return result
    else:
        # セッションIDが無い場合は新規セッションを作成
        generated_session_id = f"local_import_{uuid.uuid4().hex}"
        session = PickerSession(
            session_id=generated_session_id,
            status="expanding",
            selected_count=0,
        )
        db.session.add(session)
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            result["ok"] = False
            error_message = f"セッション作成エラー: {str(exc)}"
            result["errors"].append(error_message)
            _log_error(
                "local_import.session.create_failed",
                "ローカルインポート用セッションの作成に失敗",
                session_id=generated_session_id,
                celery_task_id=celery_task_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return result

        session_id = session.session_id
        result["session_id"] = session_id
        _log_info(
            "local_import.session.created",
            "ローカルインポート用セッションを新規作成",
            session_id=session_id,
            celery_task_id=celery_task_id,
            status="created",
        )

    active_session_id = session.session_id if session else session_id

    _set_session_progress(
        session,
        status="expanding",
        stage="expanding",
        celery_task_id=celery_task_id,
        stats_updates={
            "total": 0,
            "success": 0,
            "skipped": 0,
            "failed": 0,
        },
    )

    _log_info(
        "local_import.task.start",
        "ローカルインポートタスクを開始",
        session_id=active_session_id,
        import_dir=import_dir,
        originals_dir=originals_dir,
        celery_task_id=celery_task_id,
        status="running",
    )

    try:
        # ディレクトリの存在チェック
        if not os.path.exists(import_dir):
            if session:
                session.selected_count = 0
            _set_session_progress(
                session,
                status="error",
                stage=None,
                celery_task_id=celery_task_id,
                stats_updates={
                    "total": 0,
                    "success": 0,
                    "skipped": 0,
                    "failed": 0,
                    "reason": "import_dir_missing",
                },
            )

            result["ok"] = False
            _log_error(
                "local_import.dir.import_missing",
                "取り込み元ディレクトリが存在しません",
                import_dir=import_dir,
                session_id=active_session_id,
                celery_task_id=celery_task_id,
            )
            result["errors"].append(f"取り込みディレクトリが存在しません: {import_dir}")
            return result

        if not os.path.exists(originals_dir):
            if session:
                session.selected_count = 0
            _set_session_progress(
                session,
                status="error",
                stage=None,
                celery_task_id=celery_task_id,
                stats_updates={
                    "total": 0,
                    "success": 0,
                    "skipped": 0,
                    "failed": 0,
                    "reason": "destination_dir_missing",
                },
            )

            result["ok"] = False
            _log_error(
                "local_import.dir.destination_missing",
                "保存先ディレクトリが存在しません",
                originals_dir=originals_dir,
                session_id=active_session_id,
                celery_task_id=celery_task_id,
            )
            result["errors"].append(f"保存先ディレクトリが存在しません: {originals_dir}")
            return result

        # ファイル一覧の取得
        files = scan_import_directory(import_dir, session_id=active_session_id)
        _log_info(
            "local_import.scan.complete",
            "取り込み対象ファイルのスキャンが完了",
            import_dir=import_dir,
            total=len(files),
            samples=files[:5],
            session_id=active_session_id,
            celery_task_id=celery_task_id,
            status="scanned",
        )

        total_files = len(files)

        if total_files == 0:
            if session:
                session.selected_count = 0
            _set_session_progress(
                session,
                status="error",
                stage=None,
                celery_task_id=celery_task_id,
                stats_updates={
                    "total": 0,
                    "success": 0,
                    "skipped": 0,
                    "failed": 0,
                    "reason": "no_files_found",
                },
            )

            _log_warning(
                "local_import.scan.empty",
                "取り込み対象ファイルが存在しませんでした",
                import_dir=import_dir,
                session_id=active_session_id,
                celery_task_id=celery_task_id,
                status="empty",
            )
            result["ok"] = False
            result["errors"].append(f"取り込み対象ファイルが見つかりません: {import_dir}")
            return result

        enqueued_count = _enqueue_local_import_selections(
            session,
            files,
            active_session_id=active_session_id,
            celery_task_id=celery_task_id,
        )

        pending_total = 0
        if session:
            pending_total = _pending_selections_query(session).count()

        _set_session_progress(
            session,
            status="processing",
            stage="progress",
            celery_task_id=celery_task_id,
            stats_updates={
                "total": pending_total,
                "success": 0,
                "skipped": 0,
                "failed": 0,
            },
        )

        _log_info(
            "local_import.queue.prepared",
            "取り込み処理キューを準備",
            enqueued=enqueued_count,
            pending=pending_total,
            session_id=active_session_id,
            celery_task_id=celery_task_id,
            status="queued",
        )

        _process_local_import_queue(
            session,
            import_dir=import_dir,
            originals_dir=originals_dir,
            result=result,
            active_session_id=active_session_id,
            celery_task_id=celery_task_id,
            task_instance=task_instance,
        )
        
    except Exception as e:
        result["ok"] = False
        result["errors"].append(f"取り込み処理でエラーが発生しました: {str(e)}")
        _log_error(
            "local_import.task.failed",
            "ローカルインポート処理中に予期しないエラーが発生",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
            session_id=active_session_id,
            celery_task_id=celery_task_id,
        )
    finally:
        _cleanup_extracted_directories()

    # セッションステータスの更新
    if session:
        try:
            counts_query = (
                db.session.query(
                    PickerSelection.status,
                    db.func.count(PickerSelection.id)
                )
                .filter(PickerSelection.session_id == session.id)
                .group_by(PickerSelection.status)
                .all()
            )
            counts_map = {row[0]: row[1] for row in counts_query}

            pending_remaining = sum(
                counts_map.get(status, 0) for status in ("pending", "enqueued", "running")
            )
            imported_count = counts_map.get("imported", 0)
            dup_count = counts_map.get("dup", 0)
            skipped_count = counts_map.get("skipped", 0)
            failed_count = counts_map.get("failed", 0)

            result["success"] = imported_count
            result["skipped"] = dup_count + skipped_count
            result["failed"] = failed_count
            result["processed"] = imported_count + dup_count + skipped_count + failed_count

            cancel_requested = bool(result.get("canceled")) or _session_cancel_requested(session)

            recorded_thumbnails = result.get("thumbnail_records")
            thumbnail_snapshot = build_thumbnail_task_snapshot(session, recorded_thumbnails)
            result["thumbnail_snapshot"] = thumbnail_snapshot
            thumbnail_status = thumbnail_snapshot.get("status") if isinstance(thumbnail_snapshot, dict) else None

            thumbnails_pending = thumbnail_status == "progress"
            thumbnails_failed = thumbnail_status == "error"

            if cancel_requested:
                final_status = "canceled"
            elif pending_remaining > 0 or thumbnails_pending:
                final_status = "processing"
            else:
                if (not result["ok"]) or result["failed"] > 0 or thumbnails_failed:
                    final_status = "error"
                elif result["success"] > 0 or result["skipped"] > 0 or result["processed"] > 0:
                    final_status = "imported"
                else:
                    final_status = "ready"

            session.selected_count = imported_count

            stats = {
                "total": result["processed"],
                "success": result["success"],
                "skipped": result["skipped"],
                "failed": result["failed"],
                "pending": pending_remaining,
                "celery_task_id": celery_task_id,
            }

            import_task_status = "canceled" if cancel_requested else None
            if import_task_status is None:
                if pending_remaining > 0:
                    import_task_status = "progress"
                elif result["failed"] > 0 or not result["ok"]:
                    import_task_status = "error"
                elif result["processed"] > 0:
                    import_task_status = "completed"
                else:
                    import_task_status = "idle"

            tasks_payload: List[Dict[str, Any]] = [
                {
                    "key": "import",
                    "label": "File Import",
                    "status": import_task_status,
                    "counts": {
                        "total": result["processed"],
                        "success": result["success"],
                        "skipped": result["skipped"],
                        "failed": result["failed"],
                        "pending": pending_remaining,
                    },
                }
            ]

            if isinstance(thumbnail_snapshot, dict):
                stats["thumbnails"] = thumbnail_snapshot
                if thumbnail_snapshot.get("total") or thumbnail_snapshot.get("status") not in {None, "idle"}:
                    tasks_payload.append(
                        {
                            "key": "thumbnails",
                            "label": "Thumbnail Generation",
                            "status": thumbnail_snapshot.get("status"),
                            "counts": {
                                "total": thumbnail_snapshot.get("total"),
                                "completed": thumbnail_snapshot.get("completed"),
                                "pending": thumbnail_snapshot.get("pending"),
                                "failed": thumbnail_snapshot.get("failed"),
                            },
                            "entries": thumbnail_snapshot.get("entries"),
                        }
                    )

            if tasks_payload:
                stats["tasks"] = tasks_payload

            stage_value = "canceled" if cancel_requested else None
            if stage_value != "canceled":
                if thumbnails_failed:
                    stage_value = "error"
                elif pending_remaining > 0 or thumbnails_pending:
                    stage_value = "progress"
                else:
                    stage_value = "completed"
            if cancel_requested:
                stats.update(
                    {
                        "cancel_requested": False,
                        "canceled_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    }
                )

            _set_session_progress(
                session,
                status=final_status,
                stage=stage_value,
                celery_task_id=celery_task_id,
                stats_updates=stats,
            )

            _log_info(
                "local_import.session.updated",
                "セッション情報を更新",
                session_id=session.session_id,
                status=final_status,
                stats=stats,
                celery_task_id=celery_task_id,
            )
        except Exception as e:
            result["errors"].append(f"セッション更新エラー: {str(e)}")
            _log_error(
                "local_import.session.update_failed",
                "セッション更新時にエラーが発生",
                session_id=session.session_id if session else None,
                error_type=type(e).__name__,
                error_message=str(e),
                celery_task_id=celery_task_id,
            )

    _log_info(
        "local_import.task.summary",
        "ローカルインポートタスクが完了",
        ok=result["ok"],
        processed=result["processed"],
        success=result["success"],
        skipped=result["skipped"],
        failed=result["failed"],
        canceled=result.get("canceled", False),
        session_id=result.get("session_id"),
        celery_task_id=celery_task_id,
        status="completed" if result.get("ok") else "error",
    )

    return result


if __name__ == "__main__":
    # テスト実行用
    from webapp import create_app
    
    app = create_app()
    with app.app_context():
        result = local_import_task()
        print(f"処理結果: {result}")
