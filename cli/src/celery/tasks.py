"""Celery background tasks."""

from .celery_app import celery
from pathlib import Path
import hashlib
import time
import requests

from core.tasks.picker_import import picker_import_watchdog, picker_import_item
from core.tasks.local_import import local_import_task
from core.tasks.session_recovery import cleanup_stale_sessions, force_cleanup_all_processing_sessions


def _save_content(path: Path, content: bytes) -> None:
    """ファイルへ内容を書き込むヘルパー関数。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(content)


def _download_content(url: str) -> tuple[bytes, str]:
    """URL からコンテンツを取得し内容とハッシュを返す。"""
    resp = requests.get(url)
    resp.raise_for_status()
    content = resp.content
    sha = hashlib.sha256(content).hexdigest()
    return content, sha


@celery.task(bind=True)
def dummy_long_task(self, x, y):
    """擬似的に長時間処理を行うサンプルタスク。"""
    time.sleep(5)
    return {"result": x + y}


@celery.task(bind=True)
def download_file(self, url: str, dest_dir: str) -> dict:
    """指定した URL をダウンロードし保存するタスク。"""
    content, sha = _download_content(url)
    tmp_name = hashlib.sha1(url.encode("utf-8")).hexdigest()
    dest_path = Path(dest_dir) / tmp_name
    _save_content(dest_path, content)
    return {"path": str(dest_path), "bytes": len(content), "sha256": sha}


@celery.task(bind=True, name="picker_import.item")
def picker_import_item_task(self, selection_id: int, session_id: int) -> dict:
    """Run picker import for a single selection."""
    return picker_import_item(selection_id=selection_id, session_id=session_id)


@celery.task(name="picker_import.watchdog")
def picker_import_watchdog_task():
    return picker_import_watchdog()


@celery.task(bind=True, name="local_import.run")
def local_import_task_celery(self, session_id=None):
    """ローカルファイル取り込みタスク"""
    return local_import_task(task_instance=self, session_id=session_id)


@celery.task(bind=True, name="session_recovery.cleanup_stale_sessions")
def cleanup_stale_sessions_task(self):
    """定期的に古い処理中セッションをクリーンアップする"""
    return cleanup_stale_sessions()


@celery.task(bind=True, name="session_recovery.force_cleanup_all")
def force_cleanup_all_sessions_task(self):
    """全ての処理中セッションを強制的にクリーンアップする（緊急時用）"""
    return force_cleanup_all_processing_sessions()


__all__ = [
    "dummy_long_task",
    "download_file",
    "picker_import_item_task",
    "picker_import_watchdog_task",
    "local_import_task_celery",
    "cleanup_stale_sessions_task",
    "force_cleanup_all_sessions_task",
]
