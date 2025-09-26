from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def app(tmp_path):
    """Create an application with isolated storage directories for testing."""

    db_path = tmp_path / "test.db"
    orig = tmp_path / "orig"
    play = tmp_path / "play"
    thumbs = tmp_path / "thumbs"
    orig.mkdir()
    play.mkdir()
    thumbs.mkdir()

    env_keys = {
        "SECRET_KEY": "test",
        "DATABASE_URI": f"sqlite:///{db_path}",
        "FPV_NAS_ORIGINALS_DIR": str(orig),
        "FPV_NAS_PLAY_DIR": str(play),
        "FPV_NAS_THUMBS_DIR": str(thumbs),
    }
    prev_env = {k: os.environ.get(k) for k in env_keys}
    os.environ.update(env_keys)

    import webapp.config as config_module
    import webapp as webapp_module

    importlib.reload(config_module)
    importlib.reload(webapp_module)

    from webapp.config import Config

    Config.SQLALCHEMY_ENGINE_OPTIONS = {}

    from webapp import create_app

    app = create_app()
    app.config.update(TESTING=True)

    from webapp.extensions import db

    with app.app_context():
        db.create_all()

    yield app

    with app.app_context():
        from webapp.extensions import db as db_ext

        db_ext.session.remove()
        db_ext.drop_all()

    for module in ("webapp.config", "webapp"):
        sys.modules.pop(module, None)

    for key, value in prev_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.mark.usefixtures("app")
def test_enqueue_media_playback_generates_thumbnails_for_completed_playback(app, monkeypatch):
    """Ensure completed playbacks backfill thumbnails when requested again."""

    from core.tasks import media_post_processing

    monkeypatch.setattr(media_post_processing.shutil, "which", lambda _: "/usr/bin/ffmpeg")

    play_dir = Path(os.environ["FPV_NAS_PLAY_DIR"])
    thumbs_dir = Path(os.environ["FPV_NAS_THUMBS_DIR"])

    poster_rel = "2025/09/27/video.jpg"
    poster_path = play_dir / poster_rel
    poster_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1280, 720), color=(10, 20, 30)).save(poster_path)

    from webapp.extensions import db
    from core.models.photo_models import Media, MediaPlayback

    with app.app_context():
        media = Media(
            google_media_id="vid-123",
            account_id=None,
            local_rel_path="2025/09/27/video.mp4",
            filename="video.mp4",
            hash_sha256="0" * 64,
            bytes=1024,
            mime_type="video/mp4",
            width=1280,
            height=720,
            shot_at=datetime(2025, 9, 27, tzinfo=timezone.utc),
            imported_at=datetime(2025, 9, 27, tzinfo=timezone.utc),
            orientation=None,
            is_video=True,
            is_deleted=False,
            has_playback=True,
        )
        db.session.add(media)
        db.session.commit()

        playback = MediaPlayback(
            media_id=media.id,
            preset="std1080p",
            rel_path="2025/09/27/video.mp4",
            poster_rel_path=poster_rel,
            status="done",
        )
        db.session.add(playback)
        db.session.commit()

        result = media_post_processing.enqueue_media_playback(media.id)
        assert result["ok"] is True
        assert result["note"] == "already_done"
        assert result["playback_status"] == "done"
        assert "thumbnails" in result
        assert result["thumbnails"].get("ok") is True

        db.session.refresh(media)
        assert media.thumbnail_rel_path == "2025/09/27/video.jpg"

    thumb_path = thumbs_dir / "256" / "2025/09/27/video.jpg"
    assert thumb_path.exists()

