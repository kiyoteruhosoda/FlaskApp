"""ローカルファイル取り込みタスク."""

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.db import db
from core.models.photo_models import (
    Media,
    MediaItem,
    MediaPlayback,
    PickerSelection,
)
from core.models.picker_session import PickerSession
from core.logging_config import setup_task_logging
from core.storage_paths import first_existing_storage_path, storage_path_candidates
from core.tasks.media_post_processing import (
    enqueue_media_playback,
    enqueue_thumbs_generate,
    process_media_post_import,
)
from core.tasks.thumbs_generate import (
    PLAYBACK_NOT_READY_NOTES,
    thumbs_generate as _thumbs_generate,
)
from webapp.config import Config

from application.local_import.file_importer import (
    LocalImportFileImporter,
    PlaybackError as _PlaybackError,
)
from application.local_import.logger import LocalImportTaskLogger
from application.local_import.queue import LocalImportQueueProcessor
from application.local_import.scanner import ImportDirectoryScanner
from application.local_import.use_case import LocalImportUseCase
from application.local_import.results import build_thumbnail_task_snapshot as _build_thumbnail_task_snapshot
from domain.local_import.media_entities import (
    apply_analysis_to_media_entity,
    build_media_from_analysis,
    build_media_item_from_analysis,
    ensure_exif_for_media,
    update_media_item_from_analysis,
)
from domain.local_import.media_file import (
    DefaultMediaMetadataProvider,
    MediaFileAnalyzer,
)
from domain.local_import.media_metadata import (
    calculate_file_hash,
    extract_exif_data,
    extract_video_metadata as _extract_video_metadata,
    get_image_dimensions,
)
from domain.local_import.policies import SUPPORTED_EXTENSIONS
from domain.local_import.zip_archive import ZipArchiveService
from domain.local_import.session import LocalImportSessionService

# Re-export ``thumbs_generate`` so tests can monkeypatch the function without
# reaching into the deeper module.  The helper is still invoked via
# :func:`_regenerate_duplicate_video_thumbnails` but can be swapped out in
# environments where the heavy thumbnail pipeline is not available (for
# example in SQLite based test runs).
thumbs_generate = _thumbs_generate
extract_video_metadata = _extract_video_metadata

# Setup logger for this module - use Celery task logger for consistency
logger = setup_task_logging(__name__)
# Also get celery task logger for cross-compatibility
celery_logger = logging.getLogger('celery.task.local_import')


LocalImportPlaybackError = _PlaybackError


_task_logger = LocalImportTaskLogger(logger, celery_logger)


def _log_info(
    event: str,
    message: str,
    *,
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    **details: Any,
) -> None:
    """情報ログを記録。"""

    _task_logger.info(
        event,
        message,
        session_id=session_id,
        status=status,
        **details,
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

    _task_logger.warning(
        event,
        message,
        session_id=session_id,
        status=status,
        **details,
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
    _task_logger.error(
        event,
        message,
        session_id=session_id,
        status=status_value,
        exc_info=exc_info,
        **details,
    )


def _playback_storage_root() -> Optional[Path]:
    """Resolve the playback storage root directory."""

    base = first_existing_storage_path("FPV_NAS_PLAY_DIR")
    if not base:
        candidates = storage_path_candidates("FPV_NAS_PLAY_DIR")
        base = candidates[0] if candidates else None
    if not base:
        return None
    return Path(base)


def _clean_relative_path(rel_path: str) -> Path:
    """Return a sanitised ``Path`` for the stored relative path."""

    candidate = Path(rel_path.replace("\\", "/"))
    parts: List[str] = []
    for part in candidate.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            continue
        parts.append(part)
    return Path(*parts)


def _rebase_relative_path(
    new_relative_path: str,
    current_rel: str,
    *,
    old_relative_path: Optional[str],
) -> str:
    """Rebase *current_rel* so that it lives alongside *new_relative_path*."""

    current = _clean_relative_path(current_rel)
    if not current.parts:
        return current_rel

    current_name = current.name
    remainder = ""
    if old_relative_path:
        old_base = _clean_relative_path(old_relative_path).stem
        if old_base and current_name.startswith(old_base):
            remainder = current_name[len(old_base) :]

    destination_base = _clean_relative_path(new_relative_path)
    new_base_name = destination_base.stem
    if remainder:
        new_name = new_base_name + remainder
    else:
        suffix = Path(current_name).suffix
        if suffix:
            new_name = Path(new_base_name).with_suffix(suffix).name
        else:
            new_name = new_base_name

    destination = _clean_relative_path(new_relative_path)
    parent = destination.parent
    if not destination.parts or str(parent) == ".":
        rebased = Path(new_name)
    else:
        rebased = parent / new_name
    return rebased.as_posix()


def _relocate_playback_asset(
    base_dir: Path,
    *,
    old_rel: str,
    new_rel: str,
    media_id: int,
    session_id: Optional[str],
    asset_type: str,
) -> bool:
    """Move a playback asset from *old_rel* to *new_rel* under *base_dir*."""

    old_path = base_dir / _clean_relative_path(old_rel)
    new_path = base_dir / _clean_relative_path(new_rel)

    if old_path == new_path:
        return False

    if not old_path.exists():
        _log_warning(
            "local_import.file.duplicate_playback_asset_missing",
            "再生アセットの移動元が見つかりません",
            media_id=media_id,
            asset_type=asset_type,
            old_rel_path=old_rel,
            new_rel_path=new_rel,
            session_id=session_id,
            status="missing",
        )
        return False

    new_path.parent.mkdir(parents=True, exist_ok=True)
    moved = False
    try:
        shutil.move(str(old_path), str(new_path))
        moved = True
    except OSError:
        shutil.copy2(str(old_path), str(new_path))
    if not moved:
        try:
            os.remove(str(old_path))
        except OSError:
            pass
    return True


def _update_media_playback_paths(
    media: Media,
    *,
    old_relative_path: Optional[str],
    new_relative_path: str,
    session_id: Optional[str] = None,
    playback_entries: Optional[List[MediaPlayback]] = None,
) -> None:
    """Update playback asset paths so they mirror *new_relative_path*."""

    playback_root = _playback_storage_root()
    if not playback_root:
        _log_warning(
            "local_import.file.duplicate_playback_base_missing",
            "再生アセットの保存先を特定できません",
            media_id=media.id,
            old_relative_path=old_relative_path,
            new_relative_path=new_relative_path,
            session_id=session_id,
            status="playback_base_missing",
        )
        return

    if playback_entries is None:
        playback_entries = MediaPlayback.query.filter_by(media_id=media.id).all()
    if not playback_entries:
        return

    playback_root.mkdir(parents=True, exist_ok=True)
    relocated = 0

    for pb in playback_entries:
        current_rel = pb.rel_path or ""
        if current_rel:
            rebased_rel = _rebase_relative_path(
                new_relative_path,
                current_rel,
                old_relative_path=old_relative_path,
            )
            if rebased_rel != current_rel:
                if _relocate_playback_asset(
                    playback_root,
                    old_rel=current_rel,
                    new_rel=rebased_rel,
                    media_id=media.id,
                    session_id=session_id,
                    asset_type="playback",
                ):
                    relocated += 1
            pb.rel_path = rebased_rel
        poster_rel = pb.poster_rel_path or ""
        if poster_rel:
            rebased_poster = _rebase_relative_path(
                new_relative_path,
                poster_rel,
                old_relative_path=old_relative_path,
            )
            if rebased_poster != poster_rel:
                if _relocate_playback_asset(
                    playback_root,
                    old_rel=poster_rel,
                    new_rel=rebased_poster,
                    media_id=media.id,
                    session_id=session_id,
                    asset_type="poster",
                ):
                    relocated += 1
            pb.poster_rel_path = rebased_poster
        pb.updated_at = datetime.now(timezone.utc)

    if relocated:
        _log_info(
            "local_import.file.duplicate_playback_path_updated",
            "重複メディアの再生アセットの保存先パスを更新",
            media_id=media.id,
            old_relative_path=old_relative_path,
            new_relative_path=new_relative_path,
            session_id=session_id,
            status="playback_path_updated",
            relocated_assets=relocated,
        )


def _playback_paths_need_alignment(
    playback_entries: Iterable[MediaPlayback],
    new_relative_path: str,
) -> bool:
    """Return ``True`` if any playback asset path conflicts with the new layout."""

    if not new_relative_path:
        return False

    target_path = _clean_relative_path(new_relative_path)
    if not target_path.parts:
        return False

    target_parent = target_path.parent
    target_parent_str = "" if str(target_parent) == "." else target_parent.as_posix()
    target_base = target_path.stem

    for pb in playback_entries:
        for rel in (pb.rel_path, pb.poster_rel_path):
            if not rel:
                continue
            cleaned = _clean_relative_path(rel)
            if not cleaned.parts:
                continue
            current_parent = cleaned.parent
            current_parent_str = (
                "" if str(current_parent) == "." else current_parent.as_posix()
            )
            if current_parent_str != target_parent_str:
                return True
            current_base = cleaned.stem
            if (
                target_base
                and current_base
                and not current_base.startswith(target_base)
            ):
                return True

    return False


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

    _task_logger.commit_with_error_logging(
        db,
        event,
        message,
        session_id=session_id,
        celery_task_id=celery_task_id,
        exc_info=exc_info,
        **details,
    )


_session_service = LocalImportSessionService(db, _log_error)


_zip_service = ZipArchiveService(
    _log_info,
    _log_warning,
    _log_error,
    SUPPORTED_EXTENSIONS,
)


_scanner = ImportDirectoryScanner(
    logger=_task_logger,
    zip_service=_zip_service,
    supported_extensions=SUPPORTED_EXTENSIONS,
)


class _LocalImportMetadataProvider(DefaultMediaMetadataProvider):
    """テストでのモンキーパッチを尊重するためのメタデータプロバイダ."""

    def calculate_file_hash(self, file_path: str) -> str:
        return calculate_file_hash(file_path)

    def extract_exif_data(self, file_path: str):
        return extract_exif_data(file_path)

    def extract_video_metadata(self, file_path: str) -> Dict[str, Any]:
        return extract_video_metadata(file_path)

    def get_image_dimensions(self, file_path: str):
        return get_image_dimensions(file_path)


_media_analyzer = MediaFileAnalyzer(metadata_provider=_LocalImportMetadataProvider())


def _cleanup_extracted_directories() -> None:
    """ZIP展開で生成されたディレクトリを削除。"""

    _scanner.cleanup()


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

    analysis = _media_analyzer.analyze(source_path)

    old_relative_path = media.local_rel_path or None
    new_relative_path = analysis.relative_path
    destination_path: Optional[str] = None

    if new_relative_path:
        destination_path = os.path.normpath(
            os.path.join(originals_dir, new_relative_path)
        )
        source_absolute = os.path.normpath(source_path)
        old_absolute = (
            os.path.normpath(os.path.join(originals_dir, old_relative_path))
            if old_relative_path
            else None
        )

        if old_absolute != destination_path:
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            relocation_source = None
            if old_absolute and os.path.exists(old_absolute):
                relocation_source = old_absolute
            elif os.path.exists(source_absolute):
                relocation_source = source_absolute

            if relocation_source and relocation_source != destination_path:
                moved = False
                try:
                    shutil.move(relocation_source, destination_path)
                    moved = True
                except OSError:
                    shutil.copy2(relocation_source, destination_path)
                if not moved and relocation_source != destination_path:
                    if relocation_source == old_absolute and os.path.exists(relocation_source):
                        try:
                            os.remove(relocation_source)
                        except OSError:
                            pass
                if (
                    old_absolute
                    and old_absolute != destination_path
                    and os.path.exists(old_absolute)
                ):
                    try:
                        os.remove(old_absolute)
                    except OSError:
                        pass

        media.local_rel_path = new_relative_path

        playback_entries: List[MediaPlayback] = []
        if media.id:
            playback_entries = MediaPlayback.query.filter_by(media_id=media.id).all()

        relative_path_changed = old_relative_path != new_relative_path
        playback_alignment_needed = bool(
            playback_entries
            and _playback_paths_need_alignment(playback_entries, new_relative_path)
        )

        if relative_path_changed:
            _log_info(
                "local_import.file.duplicate_path_updated",
                "重複メディアの保存先パスを更新",
                media_id=media.id,
                old_relative_path=old_relative_path,
                new_relative_path=new_relative_path,
                session_id=session_id,
                status="path_updated",
            )
        elif playback_alignment_needed:
            _log_info(
                "local_import.file.duplicate_playback_path_realigned",
                "重複メディアの再生アセットの保存先パスを撮影日時に合わせて補正",
                media_id=media.id,
                relative_path=new_relative_path,
                session_id=session_id,
                status="playback_path_realigned",
            )

        _update_media_playback_paths(
            media,
            old_relative_path=old_relative_path,
            new_relative_path=new_relative_path,
            session_id=session_id,
            playback_entries=playback_entries or None,
        )

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
    regeneration_mode: str = "regenerate",
) -> tuple[bool, Optional[str]]:
    """重複動画のサムネイル生成を再実行する。

    Returns (success, error_message). ``success`` が False の場合は呼び出し側で
    重複取り込みをエラーとして扱い、セッションステータスに反映させる。
    """

    request_context = {"sessionId": session_id} if session_id else None

    thumb_func = thumbs_generate
    operation_id = f"duplicate-video-{media.id}"
    regen_mode_raw = regeneration_mode or "regenerate"
    if not isinstance(regen_mode_raw, str):
        regen_mode_raw = "regenerate"

    regen_mode = regen_mode_raw.strip().lower()
    if regen_mode not in {"regenerate", "skip"}:
        _log_warning(
            "local_import.duplicate_video.invalid_regeneration_mode",
            "未知の再生成モードが指定されたため既定値にフォールバックします",
            session_id=session_id,
            media_id=media.id,
            requested_mode=regen_mode_raw,
            status="invalid_regen_mode",
        )
        regen_mode = "regenerate"

    if regen_mode == "skip":
        _log_info(
            "local_import.duplicate_video.regeneration_skipped",
            "重複動画のサムネイル/再生アセット再生成がスキップされました",
            session_id=session_id,
            media_id=media.id,
            status="duplicate_regen_skipped",
        )
        return True, None

    force_playback = regen_mode == "regenerate"

    def _execute_thumb_attempt(attempt: int) -> Dict[str, Any]:
        if thumb_func is None:
            _log_info(
                "local_import.duplicate_video.thumbnail_enqueue",
                "重複動画のサムネイル再生成ジョブを投入",
                session_id=session_id,
                media_id=media.id,
                status="thumbs_regen_enqueued",
                attempt=attempt,
            )
            return enqueue_thumbs_generate(
                media.id,
                force=True,
                logger_override=logger,
                operation_id=operation_id,
                request_context=request_context,
            )

        _log_info(
            "local_import.duplicate_video.thumbnail_generate",
            "重複動画のサムネイル再生成を実行",
            session_id=session_id,
            media_id=media.id,
            status="thumbs_regen_started",
            attempt=attempt,
        )
        return thumb_func(media_id=media.id, force=True)

    def _finalise(result: Dict[str, Any], *, attempts: int) -> tuple[bool, Optional[str]]:
        paths = result.get("paths") or {}
        generated = result.get("generated", [])
        skipped = result.get("skipped", [])
        retry_details = result.get("retry_details")
        retry_blockers = result.get("retry_blockers")
        notes = result.get("notes")

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

        if retry_blockers is None and isinstance(retry_details, dict):
            maybe_blockers = retry_details.get("blockers")
            if isinstance(maybe_blockers, dict):
                retry_blockers = maybe_blockers

        if result.get("ok"):
            status = "thumbs_regenerated" if generated else "thumbs_skipped"
            _log_info(
                "local_import.duplicate_video.thumbnail_regenerated",
                "重複動画のサムネイルを再生成",
                session_id=session_id,
                media_id=media.id,
                generated=generated,
                skipped=skipped,
                notes=notes,
                generated_paths=generated_paths,
                skipped_paths=skipped_paths,
                paths=paths,
                retry_details=retry_details,
                retry_blockers=retry_blockers,
                attempts=attempts,
                status=status,
            )
            return True, None

        _log_warning(
            "local_import.duplicate_video.thumbnail_regen_skipped",
            "重複動画のサムネイル再生成をスキップ",
            session_id=session_id,
            media_id=media.id,
            generated=generated,
            skipped=skipped,
            notes=notes,
            retry_details=retry_details,
            retry_blockers=retry_blockers,
            attempts=attempts,
            status="thumbs_skipped",
        )
        return False, notes

    attempts = 0

    if force_playback:
        _log_info(
            "local_import.duplicate_video.playback_force_requested",
            "重複動画の再生アセット再生成を強制実行",
            session_id=session_id,
            media_id=media.id,
            status="playback_force_requested",
            attempts=attempts,
        )
        playback_result = enqueue_media_playback(
            media.id,
            logger_override=logger,
            operation_id=operation_id,
            request_context=request_context,
            force_regenerate=True,
        )
        if not playback_result.get("ok"):
            failure_note = playback_result.get("note") or PLAYBACK_NOT_READY_NOTES
            _log_warning(
                "local_import.duplicate_video.playback_force_failed",
                "重複動画の再生アセット強制再生成に失敗",
                session_id=session_id,
                media_id=media.id,
                note=failure_note,
                status="playback_force_failed",
                attempts=attempts,
            )
            failure_result: Dict[str, Any] = {
                "ok": False,
                "notes": failure_note,
                "generated": [],
                "skipped": [],
                "paths": {},
            }
            return _finalise(failure_result, attempts=attempts)

        _log_info(
            "local_import.duplicate_video.playback_force_completed",
            "重複動画の再生アセット再生成が完了",
            session_id=session_id,
            media_id=media.id,
            note=playback_result.get("note"),
            playback_status=playback_result.get("playback_status"),
            playback_output_path=playback_result.get("output_path"),
            playback_poster_path=playback_result.get("poster_path"),
            status="playback_force_completed",
            attempts=attempts,
        )

    attempts += 1

    try:
        result = _execute_thumb_attempt(attempts)
    except Exception as exc:  # pragma: no cover - unexpected failure path
        _log_error(
            "local_import.duplicate_video.thumbnail_regen_failed",
            "重複動画のサムネイル再生成中に例外が発生",
            session_id=session_id,
            media_id=media.id,
            error_type=type(exc).__name__,
            error_message=str(exc),
            attempt=attempts,
        )
        return False, str(exc)

    if (
        thumb_func is not None
        and result.get("ok")
        and result.get("notes") == PLAYBACK_NOT_READY_NOTES
    ):
        _log_info(
            "local_import.duplicate_video.playback_refresh_requested",
            "再生アセットを再生成してサムネイル再試行を準備",
            session_id=session_id,
            media_id=media.id,
            status="playback_refresh_requested",
            attempts=attempts,
        )
        playback_result = enqueue_media_playback(
            media.id,
            logger_override=logger,
            operation_id=operation_id,
            request_context=request_context,
        )
        if not playback_result.get("ok"):
            failure_note = playback_result.get("note") or PLAYBACK_NOT_READY_NOTES
            _log_warning(
                "local_import.duplicate_video.playback_refresh_failed",
                "重複動画の再生アセット再生成に失敗",
                session_id=session_id,
                media_id=media.id,
                note=failure_note,
                playback_output_path=playback_result.get("output_path"),
                playback_poster_path=playback_result.get("poster_path"),
                status="playback_refresh_failed",
                attempts=attempts,
            )
            failure_result: Dict[str, Any] = {
                "ok": False,
                "notes": failure_note,
                "generated": result.get("generated", []),
                "skipped": result.get("skipped", []),
                "paths": result.get("paths") or {},
            }
            return _finalise(failure_result, attempts=attempts)

        _log_info(
            "local_import.duplicate_video.playback_refreshed",
            "重複動画の再生アセット再生成が完了",
            session_id=session_id,
            media_id=media.id,
            note=playback_result.get("note"),
            playback_status=playback_result.get("playback_status"),
            playback_output_path=playback_result.get("output_path"),
            playback_poster_path=playback_result.get("poster_path"),
            status="playback_refreshed",
            attempts=attempts,
        )

        attempts += 1
        try:
            result = _execute_thumb_attempt(attempts)
        except Exception as exc:  # pragma: no cover - unexpected failure path
            _log_error(
                "local_import.duplicate_video.thumbnail_regen_failed",
                "重複動画のサムネイル再生成中に例外が発生",
                session_id=session_id,
                media_id=media.id,
                playback_output_path=playback_result.get("output_path"),
                playback_poster_path=playback_result.get("poster_path"),
                error_type=type(exc).__name__,
                error_message=str(exc),
                attempt=attempts,
            )
            return False, str(exc)

    return _finalise(result, attempts=attempts)

def import_single_file(
    file_path: str,
    import_dir: str,
    originals_dir: str,
    *,
    session_id: Optional[str] = None,
    duplicate_regeneration: Optional[str] = None,
) -> Dict:
    """単一ファイル取り込みのアプリケーションサービスへの委譲."""

    return _file_importer.import_file(
        file_path,
        import_dir,
        originals_dir,
        session_id=session_id,
        duplicate_regeneration=duplicate_regeneration,
    )


def scan_import_directory(import_dir: str, *, session_id: Optional[str] = None) -> List[str]:
    """取り込みディレクトリをスキャンするラッパー."""

    return _scanner.scan(import_dir, session_id=session_id)


def _resolve_directory(config_key: str) -> str:
    """Return a usable directory path for the given storage *config_key*."""

    path = first_existing_storage_path(config_key)
    if path:
        return path

    candidates = storage_path_candidates(config_key)
    if candidates:
        return candidates[0]

    raise RuntimeError(f"No storage directory candidates available for {config_key}")


_file_importer = LocalImportFileImporter(
    db=db,
    logger=_task_logger,
    duplicate_checker=check_duplicate_media,
    metadata_refresher=_refresh_existing_media_metadata,
    post_process_service=process_media_post_import,
    post_process_logger=logger,
    directory_resolver=_resolve_directory,
    analysis_service=_media_analyzer.analyze,
    thumbnail_regenerator=lambda media, session_id=None, regeneration_mode="regenerate": _regenerate_duplicate_video_thumbnails(
        media,
        session_id=session_id,
        regeneration_mode=regeneration_mode,
    ),
    supported_extensions=SUPPORTED_EXTENSIONS,
)

_queue_processor = LocalImportQueueProcessor(
    db=db,
    logger=_task_logger,
    importer=_file_importer,
    cancel_requested=_session_service.cancel_requested,
)

_use_case = LocalImportUseCase(
    db=db,
    logger=_task_logger,
    session_service=_session_service,
    scanner=_scanner,
    queue_processor=_queue_processor,
)


def build_thumbnail_task_snapshot(
    session: Optional[PickerSession],
    recorded_entries: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """外部から利用されるサマリ生成の互換 API."""

    return _build_thumbnail_task_snapshot(db, session, recorded_entries)


def local_import_task(task_instance=None, session_id=None) -> Dict:
    """ローカルインポートタスクをアプリケーション層に委譲する。"""

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
        request = getattr(task_instance, 'request', None)
        celery_task_id = getattr(request, 'id', None)

    result = _use_case.execute(
        session_id=session_id,
        import_dir=import_dir,
        originals_dir=originals_dir,
        celery_task_id=celery_task_id,
        task_instance=task_instance,
    )

    _cleanup_extracted_directories()
    return result


if __name__ == "__main__":
    # テスト実行用
    from webapp import create_app
    
    app = create_app()
    with app.app_context():
        result = local_import_task()
        print(f"処理結果: {result}")
