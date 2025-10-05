"""ローカルファイル取り込みタスク."""

import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.db import db
from core.models.photo_models import (
    Media,
    PickerSelection,
    MediaItem,
)
from core.models.picker_session import PickerSession
from core.logging_config import setup_task_logging
from core.storage_paths import first_existing_storage_path, storage_path_candidates
from core.tasks.media_post_processing import (
    enqueue_thumbs_generate,
    process_media_post_import,
)
from core.tasks.thumbs_generate import thumbs_generate as _thumbs_generate
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
    """単一ファイル取り込みのアプリケーションサービスへの委譲."""

    return _file_importer.import_file(
        file_path,
        import_dir,
        originals_dir,
        session_id=session_id,
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
    thumbnail_regenerator=lambda media, session_id=None: _regenerate_duplicate_video_thumbnails(
        media, session_id=session_id
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
