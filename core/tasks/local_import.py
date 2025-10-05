"""ローカルファイル取り込みタスク."""

import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from flask import current_app

from core.db import db
from core.models.photo_models import (
    Media,
    PickerSelection,
    MediaItem,
    MediaPlayback,
)
from core.models.job_sync import JobSync
from core.models.celery_task import CeleryTaskRecord, CeleryTaskStatus
from core.models.picker_session import PickerSession
from core.logging_config import log_task_error, log_task_info, setup_task_logging
from core.storage_paths import first_existing_storage_path, storage_path_candidates
from core.tasks.media_post_processing import (
    enqueue_thumbs_generate,
    process_media_post_import,
)
from core.tasks.thumbs_generate import thumbs_generate as _thumbs_generate
from webapp.config import Config

from domain.local_import.logging import (
    compose_message as _compose_message,
    existing_media_destination_context as _existing_media_destination_context,
    file_log_context as _file_log_context,
    serialize_details as _serialize_details,
    with_session as _with_session,
)
from domain.local_import.entities import ImportFile, ImportOutcome
from domain.local_import.media_entities import (
    apply_analysis_to_media_entity,
    build_media_from_analysis,
    build_media_item_from_analysis,
    ensure_exif_for_media,
    update_media_item_from_analysis,
)
from domain.local_import.media_file import analyze_media_file
from domain.local_import.policies import SUPPORTED_EXTENSIONS
from domain.local_import.zip_archive import ZipArchiveService
from domain.local_import.session import LocalImportSessionService

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


_session_service = LocalImportSessionService(db, _log_error)


_zip_service = ZipArchiveService(
    _log_info,
    _log_warning,
    _log_error,
    SUPPORTED_EXTENSIONS,
)


def _cleanup_extracted_directories() -> None:
    """ZIP展開で生成されたディレクトリを削除。"""

    _zip_service.cleanup()


def _extract_zip_archive(zip_path: str, *, session_id: Optional[str] = None) -> List[str]:
    """ZIPファイルを展開し、サポート対象ファイルのパスを返す。"""

    return _zip_service.extract(zip_path, session_id=session_id)


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

    analysis = analyze_media_file(source_path)

    apply_analysis_to_media_entity(media, analysis)

    media_item = None
    if media.google_media_id:
        media_item = MediaItem.query.get(media.google_media_id)
        if media_item:
            metadata_obj = update_media_item_from_analysis(media_item, analysis)
            if metadata_obj is not None:
                db.session.add(metadata_obj)
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
    else:
        _log_warning(
            "local_import.file.duplicate_media_item_missing",
            "既存メディアに対応するMediaItemが見つかりません",
            media_id=media.id,
            media_google_id=media.google_media_id,
            session_id=session_id,
            status="warning",
        )

    exif_model = ensure_exif_for_media(media, analysis)
    if exif_model is not None:
        db.session.add(exif_model)

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
) -> tuple[bool, Optional[str]]:
    """重複動画のサムネイル生成を再実行する。

    Returns (success, error_message). ``success`` が False の場合は呼び出し側で
    重複取り込みをエラーとして扱い、セッションステータスに反映させる。
    """

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
        return False, str(exc)

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
        return True, None

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
        return False, result.get("notes")

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
    source = ImportFile(file_path)
    outcome = ImportOutcome(
        source,
        details={
            "success": False,
            "file_path": file_path,
            "reason": "",
            "media_id": None,
            "media_google_id": None,
            "metadata_refreshed": False,
        },
    )

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
            outcome.mark("missing", reason="ファイルが存在しません")
            _log_warning(
                "local_import.file.missing",
                "取り込み対象ファイルが見つかりません",
                **file_context,
                session_id=session_id,
                status="missing",
            )
            return outcome.as_dict()

        # 拡張子チェック
        file_extension = Path(file_path).suffix.lower()
        if file_extension not in SUPPORTED_EXTENSIONS:
            outcome.mark(
                "unsupported",
                reason=f"サポートされていない拡張子: {file_extension}",
            )
            _log_warning(
                "local_import.file.unsupported",
                "サポート対象外拡張子のためスキップ",
                **file_context,
                extension=file_extension,
                session_id=session_id,
                status="unsupported",
            )
            return outcome.as_dict()

        # ファイルサイズとハッシュ計算
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            outcome.mark("skipped", reason="ファイルサイズが0です")
            _log_warning(
                "local_import.file.empty",
                "ファイルサイズが0のためスキップ",
                **file_context,
                session_id=session_id,
                status="skipped",
            )
            return outcome.as_dict()

        analysis = analyze_media_file(file_path)

        # 重複チェック
        existing_media = check_duplicate_media(analysis.file_hash, analysis.file_size)
        if existing_media:
            outcome.details.update(
                {
                    "reason": f"重複ファイル (既存ID: {existing_media.id})",
                    "media_id": existing_media.id,
                    "media_google_id": existing_media.google_media_id,
                }
            )
            outcome.mark("duplicate")

            destination_details = _existing_media_destination_context(
                existing_media, originals_dir
            )
            for key in ("imported_path", "imported_filename", "relative_path"):
                value = destination_details.get(key)
                if value:
                    outcome.details[key] = value

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
                    outcome.details["metadata_refreshed"] = True
                    outcome.details["reason"] = (
                        f"重複ファイル (既存ID: {existing_media.id}) - メタデータ更新"
                    )
                    outcome.mark("duplicate_refreshed")
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
                regen_success, regen_error = _regenerate_duplicate_video_thumbnails(
                    existing_media,
                    session_id=session_id,
                )
                if not regen_success:
                    outcome.details["thumbnail_regen_error"] = (
                        regen_error
                        or "重複動画のサムネイル再生成に失敗しました"
                    )

            return outcome.as_dict()

        is_video = analysis.is_video

        imported_filename = analysis.destination_filename
        rel_path = analysis.relative_path
        dest_path = os.path.join(originals_dir, rel_path)

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

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

        aggregate = build_media_item_from_analysis(analysis)
        db.session.add(aggregate.media_item)
        if aggregate.photo_metadata is not None:
            db.session.add(aggregate.photo_metadata)
        if aggregate.video_metadata is not None:
            db.session.add(aggregate.video_metadata)
        db.session.flush()

        media = build_media_from_analysis(
            analysis,
            google_media_id=aggregate.media_item.id,
            relative_path=rel_path,
        )
        db.session.add(media)
        db.session.flush()

        exif_model = ensure_exif_for_media(media, analysis)
        if exif_model is not None:
            db.session.add(exif_model)
        
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
            outcome.details["post_process"] = post_process_result

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
                    warnings = outcome.details.setdefault("warnings", [])
                    warnings.append(f"playback_skipped:{note}")
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

        outcome.details.update(
            {
                "success": True,
                "media_id": media.id,
                "media_google_id": media.google_media_id,
                "reason": "取り込み成功",
                "imported_filename": imported_filename,
                "imported_path": dest_path,
            }
        )
        outcome.mark("success")

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
        outcome.mark("failed", reason=f"エラー: {str(e)}")

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

    return outcome.as_dict()


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

    _session_service.set_progress(
        session,
        status=status,
        stage=stage,
        celery_task_id=celery_task_id,
        stats_updates=stats_updates,
    )


def _session_cancel_requested(
    session: Optional[PickerSession],
    *,
    task_instance=None,
) -> bool:
    """Return True when cancellation has been requested for *session*."""

    return _session_service.cancel_requested(session, task_instance=task_instance)


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
                    if file_result.get("thumbnail_regen_error"):
                        regen_message = file_result["thumbnail_regen_error"]
                        result["ok"] = False
                        result["errors"].append(
                            f"{file_path}: {regen_message}"
                        )
                        detail["notes"] = regen_message
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
                if (not result["ok"]) or result["failed"] > 0:
                    final_status = "error"
                elif thumbnails_failed:
                    final_status = "imported"
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
