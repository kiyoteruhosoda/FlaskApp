import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from core.tasks import thumbs_generate


@pytest.fixture
def app(tmp_path):
    """Create a minimal app with a temporary database and directories."""
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
        "FPV_NAS_ORIG_DIR": str(orig),
        "FPV_NAS_PLAY_DIR": str(play),
        "FPV_NAS_THUMBS_DIR": str(thumbs),
    }
    prev_env = {k: os.environ.get(k) for k in env_keys}
    os.environ.update(env_keys)

    import importlib, sys
    import webapp.config as config_module
    importlib.reload(config_module)
    import webapp as webapp_module
    importlib.reload(webapp_module)
    from webapp.config import Config
    Config.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app

    app = create_app()
    app.config.update(TESTING=True)
    from webapp.extensions import db
    from core.models.google_account import GoogleAccount

    with app.app_context():
        db.create_all()
        acc = GoogleAccount(email="acc@example.com", scopes="", oauth_token_json="{}")
        db.session.add(acc)
        db.session.commit()

    yield app
    del sys.modules["webapp.config"]
    del sys.modules["webapp"]
    for k, v in prev_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_media(app, *, rel_path: str, is_video: bool, width: int, height: int, **extra):
    from webapp.extensions import db
    from core.models.photo_models import Media

    with app.app_context():
        m = Media(
            google_media_id=rel_path,
            account_id=1,
            local_rel_path=rel_path,
            bytes=1,
            mime_type="video/mp4" if is_video else "image/jpeg",
            width=width,
            height=height,
            shot_at=datetime(2025, 8, 18, tzinfo=timezone.utc),
            imported_at=datetime(2025, 8, 18, tzinfo=timezone.utc),
            orientation=None,
            is_video=is_video,
            is_deleted=False,
            has_playback=is_video,
            **extra,
        )
        db.session.add(m)
        db.session.commit()
        return m.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_image_generation(app):
    orig_dir = Path(os.environ["FPV_NAS_ORIG_DIR"])
    path = orig_dir / "2025/08/18/img.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (4032, 3024), color=(1, 2, 3))
    exif = Image.Exif()
    exif[274] = 6  # orientation
    img.save(path, exif=exif)

    media_id = _make_media(app, rel_path="2025/08/18/img.jpg", is_video=False, width=4032, height=3024)
    with app.app_context():
        res = thumbs_generate(media_id=media_id)
    assert res == {"ok": True, "generated": [256, 1024, 2048], "skipped": [], "notes": None}

    out = Path(os.environ["FPV_NAS_THUMBS_DIR"])
    im256 = Image.open(out / "256/2025/08/18/img.jpg")
    assert im256.size == (192, 256)  # orientation applied


def test_image_skip_existing(app):
    orig_dir = Path(os.environ["FPV_NAS_ORIG_DIR"])
    path = orig_dir / "2025/08/18/img2.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (3000, 2000), color=0).save(path)
    media_id = _make_media(app, rel_path="2025/08/18/img2.jpg", is_video=False, width=3000, height=2000)

    # pre-create 1024 thumb
    out = Path(os.environ["FPV_NAS_THUMBS_DIR"])
    pre = out / "1024/2025/08/18/img2.jpg"
    pre.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1, 1)).save(pre)

    with app.app_context():
        res = thumbs_generate(media_id=media_id)
    assert res["generated"] == [256, 2048]
    assert res["skipped"] == [1024]


def test_video_with_playback(app):
    play_dir = Path(os.environ["FPV_NAS_PLAY_DIR"])
    poster_rel = "2025/08/18/poster.jpg"
    poster_path = play_dir / poster_rel
    poster_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (3000, 2000), color=(10, 20, 30)).save(poster_path)

    media_id = _make_media(app, rel_path="2025/08/18/video.mp4", is_video=True, width=3000, height=2000)

    from webapp.extensions import db
    from core.models.photo_models import MediaPlayback
    with app.app_context():
        pb = MediaPlayback(
            media_id=media_id,
            preset="std1080p",
            rel_path="2025/08/18/video.mp4",
            poster_rel_path=poster_rel,
            status="done",
        )
        db.session.add(pb)
        db.session.commit()

    with app.app_context():
        res = thumbs_generate(media_id=media_id)
    assert res["generated"] == [256, 1024, 2048]
    out = Path(os.environ["FPV_NAS_THUMBS_DIR"])
    assert (out / "256/2025/08/18/video.jpg").exists()


def test_video_playback_not_ready(app):
    media_id = _make_media(app, rel_path="2025/08/18/vid2.mp4", is_video=True, width=3000, height=2000)
    with app.app_context():
        res = thumbs_generate(media_id=media_id)
    assert res == {
        "ok": True,
        "generated": [],
        "skipped": [256, 1024, 2048],
        "notes": "playback not ready",
    }
