"""Celery background tasks."""

from .celery_app import celery
from pathlib import Path
import hashlib
import time
import requests


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


__all__ = ["dummy_long_task", "download_file"]
