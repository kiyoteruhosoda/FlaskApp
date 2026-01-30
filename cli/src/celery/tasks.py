"""Celery background tasks."""

import logging
from pathlib import Path
import hashlib
import time
import requests


DEFAULT_DOWNLOAD_TIMEOUT = 30

from core.tasks.picker_import import picker_import_watchdog, picker_import_item
from core.tasks.local_import import local_import_task
from core.tasks.session_recovery import (
    cleanup_stale_sessions,
    force_cleanup_all_processing_sessions,
    get_session_status_report
)
from core.tasks.backup_cleanup import cleanup_old_backups, get_backup_status
from core.tasks.log_cleanup import cleanup_old_logs
from core.tasks.media_post_processing import process_due_thumbnail_retries
from core.logging_config import log_task_info, log_task_error
from core.tasks.thumbs_generate import (
    PLAYBACK_NOT_READY_NOTES,
    PlaybackNotReadyError,
    thumbs_generate,
)
from bounded_contexts.certs.tasks.rotate_certificates import (  # noqa: F401 - タスク登録目的
    auto_rotate_certificates_task,
)

from .celery_app import celery

# Celery task logger
logger = logging.getLogger('celery.task')


def _save_content(path: Path, content: bytes) -> None:
    """ファイルへ内容を書き込むヘルパー関数。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)


def _download_content(url: str, timeout: float = DEFAULT_DOWNLOAD_TIMEOUT) -> tuple[bytes, str]:
    """URL からコンテンツを取得し内容とハッシュを返す。"""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    content = resp.content
    sha = hashlib.sha256(content).hexdigest()
    return content, sha


THUMBNAIL_RETRY_COUNTDOWN = 300


@celery.task(bind=True)
def dummy_long_task(self, x, y):
    """擬似的に長時間処理を行うサンプルタスク。"""
    try:
        # Test for intentional error
        if isinstance(y, str):
            raise ValueError(f"Invalid type for y: {type(y)}")
            
        time.sleep(2)  # Reduced sleep time for testing
        result = x + y
        
        # Log success
        log_task_info(logger, f"Dummy task completed successfully: {x} + {y} = {result}", 
                     event="dummy_task_success", x=x, y=y, result=result)
        
        return {"ok": True, "result": result}
    except Exception as e:
        self.log_error(f"Dummy task failed: {str(e)}", event="dummy_task_error", exc_info=True)
        return {"ok": False, "error": str(e)}


@celery.task(bind=True)
def download_file(self, url: str, dest_dir: str, timeout: float = DEFAULT_DOWNLOAD_TIMEOUT) -> dict:
    """指定した URL をダウンロードし保存するタスク。"""
    try:
        content, sha = _download_content(url, timeout=timeout)
        tmp_name = hashlib.sha1(url.encode("utf-8")).hexdigest()
        dest_path = Path(dest_dir) / tmp_name
        _save_content(dest_path, content)
        return {"path": str(dest_path), "bytes": len(content), "sha256": sha}
    except Exception as e:
        self.log_error(f"Download file failed for {url}: {str(e)}", event="download_file", exc_info=True)
        return {"ok": False, "error": str(e)}


@celery.task(bind=True, name="thumbs.generate")
def thumbs_generate_task(self, media_id: int, force: bool = False, retry_countdown: int = THUMBNAIL_RETRY_COUNTDOWN) -> dict:
    """Generate thumbnails via Celery with automatic retry for playback readiness."""

    try:
        result = thumbs_generate(media_id=media_id, force=force)
    except Exception as exc:  # pragma: no cover - unexpected failure path
        self.log_error(
            f"Thumbnail generation raised an exception for media {media_id}: {exc}",
            event="thumbs_generate.exception",
            exc_info=True,
            media_id=media_id,
        )
        return {"ok": False, "error": str(exc)}

    if result.get("ok") and result.get("notes") == PLAYBACK_NOT_READY_NOTES:
        log_task_info(
            logger,
            "Playback not ready for thumbnail generation; retry scheduled.",
            event="thumbs_generate.retry_scheduled",
            media_id=media_id,
            countdown=retry_countdown,
            force=force,
        )
        raise self.retry(
            countdown=retry_countdown,
            exc=PlaybackNotReadyError(PLAYBACK_NOT_READY_NOTES),
            max_retries=None,
        )

    if result.get("ok"):
        log_task_info(
            logger,
            "Thumbnail generation completed via Celery.",
            event="thumbs_generate.success",
            media_id=media_id,
            generated=result.get("generated"),
            skipped=result.get("skipped"),
        )
    else:
        log_task_error(
            logger,
            "Thumbnail generation reported failure.",
            event="thumbs_generate.failed",
            media_id=media_id,
            notes=result.get("notes"),
        )

    return result


@celery.task(bind=True, name="picker_import.item")
def picker_import_item_task(self, selection_id: int, session_id: int) -> dict:
    """Run picker import for a single selection."""
    try:
        return picker_import_item(selection_id=selection_id, session_id=session_id)
    except Exception as e:
        self.log_error(
            f"Picker import item failed (selection_id={selection_id}, session_id={session_id}): {str(e)}",
            event="import.picker.item",
            exc_info=True,
        )
        return {"ok": False, "error": str(e)}


@celery.task(name="picker_import.watchdog")
def picker_import_watchdog_task():
    try:
        return picker_import_watchdog()
    except Exception as e:
        logger.error(
            f"Picker import watchdog failed: {str(e)}",
            extra={'event': 'import.picker.watchdog'},
            exc_info=True,
        )
        return {"ok": False, "error": str(e)}


@celery.task(bind=True, name="local_import.run")
def local_import_task_celery(self, session_id=None):
    """ローカルファイル取り込みタスク"""
    celery_task_id = getattr(getattr(self, "request", None), "id", None)
    log_task_info(
        logger,
        "Local import Celery task invoked",
        event="local_import.celery.start",
        session_id=session_id,
        celery_task_id=celery_task_id,
    )
    try:
        result = local_import_task(task_instance=self, session_id=session_id)
    except Exception as e:
        self.log_error(f"Local import task failed (session_id={session_id}): {str(e)}",
                      event="local_import", exc_info=True)
        return {"ok": False, "error": str(e)}
    else:
        log_task_info(
            logger,
            "Local import Celery task finished",
            event="local_import.celery.finish",
            session_id=session_id,
            celery_task_id=celery_task_id,
            ok=result.get("ok"),
            processed=result.get("processed"),
            success=result.get("success"),
            skipped=result.get("skipped"),
            failed=result.get("failed"),
        )
        return result


@celery.task(bind=True, name="session_recovery.cleanup_stale_sessions")
def cleanup_stale_sessions_task(self):
    """定期的に古い処理中セッションをクリーンアップする"""
    try:
        return cleanup_stale_sessions()
    except Exception as e:
        self.log_error(f"Cleanup stale sessions failed: {str(e)}",
                      event="session_recovery_cleanup", exc_info=True)
        return {"ok": False, "error": str(e)}


@celery.task(bind=True, name="logs.cleanup")
def cleanup_old_logs_task(self, retention_days: int = 365):
    """Delete log and picker session records older than the retention period."""
    try:
        return cleanup_old_logs(retention_days=retention_days)
    except Exception as e:  # pragma: no cover - defensive path
        self.log_error(
            f"Log cleanup failed: {str(e)}",
            event="logs_cleanup",
            exc_info=True,
            retention_days=retention_days,
        )
        return {"ok": False, "error": str(e)}


@celery.task(bind=True, name="thumbnail_retry.process_due")
def thumbnail_retry_process_task(self, limit: int = 50):
    """Process thumbnail retry records whose scheduled time has elapsed."""

    try:
        return process_due_thumbnail_retries(limit=limit)
    except Exception as e:
        self.log_error(
            f"Thumbnail retry monitor failed: {str(e)}",
            event="thumbnail_retry_process",
            exc_info=True,
        )
        return {"ok": False, "error": str(e)}


@celery.task(bind=True, name="session_recovery.force_cleanup_all")
def force_cleanup_all_sessions_task(self):
    """全ての処理中セッションを強制的にクリーンアップする（緊急時用）"""
    try:
        return force_cleanup_all_processing_sessions()
    except Exception as e:
        self.log_error(f"Force cleanup all sessions failed: {str(e)}", 
                      event="session_recovery_force_cleanup", exc_info=True)
        return {"ok": False, "error": str(e)}


@celery.task(bind=True, name="session_recovery.status_report")
def session_status_report_task(self):
    """セッション状況の詳細レポートを生成する（デバッグ用）"""
    try:
        return get_session_status_report()
    except Exception as e:
        self.log_error(f"Session status report failed: {str(e)}", 
                      event="session_recovery_status", exc_info=True)
        return {"ok": False, "error": str(e)}


@celery.task(bind=True, name="backup_cleanup.cleanup")
def backup_cleanup_task(self, retention_days: int = 30):
    """古いバックアップファイルを自動削除する定期タスク
    
    Args:
        retention_days: バックアップファイルの保持日数（デフォルト: 30日）
        
    Returns:
        dict: 削除結果の詳細
    """
    try:
        return cleanup_old_backups(retention_days=retention_days)
    except Exception as e:
        self.log_error(f"Backup cleanup failed (retention_days={retention_days}): {str(e)}", 
                      event="backup_cleanup", exc_info=True)
        return {"ok": False, "error": str(e)}


@celery.task(bind=True, name="backup_cleanup.status")
def backup_status_task(self):
    """バックアップディレクトリの状況を確認する
    
    Returns:
        dict: バックアップディレクトリの詳細情報
    """
    try:
        return get_backup_status()
    except Exception as e:
        self.log_error(f"Backup status check failed: {str(e)}", 
                      event="backup_status", exc_info=True)
        return {"ok": False, "error": str(e)}


__all__ = [
    "dummy_long_task",
    "download_file",
    "thumbs_generate_task",
    "picker_import_item_task",
    "picker_import_watchdog_task",
    "local_import_task_celery",
    "cleanup_stale_sessions_task",
    "thumbnail_retry_process_task",
    "force_cleanup_all_sessions_task",
    "session_status_report_task",
    "backup_cleanup_task",
    "backup_status_task",
]
