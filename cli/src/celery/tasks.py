from pathlib import Path
from .celery_app import celery
from fpv.storage import download_to_tmp, sha256_of
from fpv.config import PhotoNestConfig
from core.tasks.thumbs_generate import thumbs_generate
from core.tasks.transcode import transcode_queue_scan, transcode_worker


def _download(url: str, tmp_dir: Path):
    """Download *url* to *tmp_dir* using fpv.storage helpers."""
    return download_to_tmp(url, tmp_dir)


def _build_result(tmp_path: Path, size: int, ctype: str) -> dict:
    """Build result dictionary including SHA-256 hash."""
    return {
        "path": str(tmp_path),
        "bytes": size,
        "sha256": sha256_of(tmp_path),
        "content_type": ctype,
    }


class Downloader:
    """Simple helper class to keep task code small."""

    def __init__(self, tmp_dir: str | None = None) -> None:
        cfg = PhotoNestConfig.from_env()
        self.tmp_dir = Path(tmp_dir or cfg.tmp_dir)

    def download(self, url: str) -> dict:
        tmp_path, size, ctype = _download(url, self.tmp_dir)
        return _build_result(tmp_path, size, ctype)


@celery.task(bind=True)
def download_file(self, url: str, tmp_dir: str | None = None) -> dict:
    """Celery task to download a URL to a temporary directory."""
    return Downloader(tmp_dir).download(url)


@celery.task(bind=True)
def generate_thumbs(self, media_id: int, force: bool = False) -> dict:
    """Celery task wrapper for thumbnail generation."""
    return thumbs_generate(media_id=media_id, force=force)


@celery.task(bind=True)
def transcode_scan(self) -> dict:
    """Celery task wrapper for transcode queue scanning."""
    return transcode_queue_scan()


@celery.task(bind=True)
def transcode_media(self, media_playback_id: int) -> dict:
    """Celery task wrapper for video transcoding."""
    return transcode_worker(media_playback_id=media_playback_id)
