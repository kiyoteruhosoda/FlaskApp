import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import shutil

import pytest

from core.tasks import transcode_queue_scan, transcode_worker


ffmpeg_missing = shutil.which("ffmpeg") is None


@pytest.fixture
def app(tmp_path):
    """Create an application with temporary directories and database."""
    db_path = tmp_path / "test.db"
    orig = tmp_path / "orig"
    play = tmp_path / "play"
    tmpd = tmp_path / "tmp"
    orig.mkdir()
    play.mkdir()
    tmpd.mkdir()

    env_keys = {
        "SECRET_KEY": "test",
        "DATABASE_URI": f"sqlite:///{db_path}",
        "FPV_NAS_ORIG_DIR": str(orig),
        "FPV_NAS_PLAY_DIR": str(play),
        "FPV_TMP_DIR": str(tmpd),
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


def _make_media(
    app,
    *,
    rel_path: str,
    width: int,
    height: int,
    has_playback: bool = False,
    **extra,
):
    from webapp.extensions import db
    from core.models.photo_models import Media

    with app.app_context():
        m = Media(
            google_media_id=rel_path,
            account_id=1,
            local_rel_path=rel_path,
            bytes=1,
            mime_type="video/mp4",
            width=width,
            height=height,
            shot_at=datetime(2025, 8, 18, tzinfo=timezone.utc),
            imported_at=datetime(2025, 8, 18, tzinfo=timezone.utc),
            orientation=None,
            is_video=True,
            is_deleted=False,
            has_playback=has_playback,
            **extra,
        )
        db.session.add(m)
        db.session.commit()
        return m.id


def _make_playback(app, media_id: int, rel_path: str, status: str = "pending") -> int:
    from webapp.extensions import db
    from core.models.photo_models import MediaPlayback

    with app.app_context():
        pb = MediaPlayback(
            media_id=media_id,
            preset="std1080p",
            rel_path=rel_path,
            status=status,
        )
        db.session.add(pb)
        db.session.commit()
        return pb.id


def _make_video(path: Path, size: str, audio: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if audio:
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={size}:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:sample_rate=48000",
            "-t",
            "1",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(path),
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={size}:rate=24",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------------------
# Queue scan tests
# ---------------------------------------------------------------------------


def test_queue_scan_basic(app):
    orig_dir = Path(os.environ["FPV_NAS_ORIG_DIR"])
    for i in range(3):
        p = orig_dir / f"2025/08/18/v{i}.mp4"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"0")
        _make_media(app, rel_path=f"2025/08/18/v{i}.mp4", width=640, height=480)

    with app.app_context():
        res = transcode_queue_scan()
        assert res == {"queued": 3, "skipped": 0, "notes": None}
        from core.models.photo_models import MediaPlayback

        assert MediaPlayback.query.count() == 3
        pb = MediaPlayback.query.first()
        assert pb.status == "pending"


def test_queue_scan_skip_existing(app):
    orig_dir = Path(os.environ["FPV_NAS_ORIG_DIR"])
    names = ["a.mp4", "b.mp4", "c.mp4"]
    ids = []
    for name in names:
        p = orig_dir / f"2025/08/18/{name}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"0")
        ids.append(_make_media(app, rel_path=f"2025/08/18/{name}", width=640, height=480))

    from webapp.extensions import db
    from core.models.photo_models import MediaPlayback
    with app.app_context():
        pb1 = MediaPlayback(media_id=ids[0], preset="std1080p", rel_path="2025/08/18/a.mp4", status="done")
        pb2 = MediaPlayback(media_id=ids[1], preset="std1080p", rel_path="2025/08/18/b.mp4", status="pending")
        pb3 = MediaPlayback(media_id=ids[2], preset="std1080p", rel_path="2025/08/18/c.mp4", status="error")
        db.session.add_all([pb1, pb2, pb3])
        db.session.commit()

        res = transcode_queue_scan()
        assert res == {"queued": 1, "skipped": 2, "notes": None}
        assert MediaPlayback.query.get(pb3.id).status == "pending"


# ---------------------------------------------------------------------------
# Worker tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_worker_transcode_basic(app):
    orig_dir = Path(os.environ["FPV_NAS_ORIG_DIR"])
    video_path = orig_dir / "2025/08/18/basic.mp4"
    _make_video(video_path, "1280x720", audio=True)
    media_id = _make_media(app, rel_path="2025/08/18/basic.mp4", width=1280, height=720)
    pb_id = _make_playback(app, media_id, "2025/08/18/basic.mp4")

    with app.app_context():
        res = transcode_worker(media_playback_id=pb_id)
        assert res["ok"] is True
        from core.models.photo_models import MediaPlayback, Media

        pb = MediaPlayback.query.get(pb_id)
        assert pb.status == "done"
        assert pb.width == 1280 and pb.height == 720
        m = Media.query.get(media_id)
        assert m.has_playback is True
        out = Path(os.environ["FPV_NAS_PLAY_DIR"]) / pb.rel_path
        assert out.exists()


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_worker_transcode_downscale(app):
    orig_dir = Path(os.environ["FPV_NAS_ORIG_DIR"])
    video_path = orig_dir / "2025/08/18/large.mp4"
    _make_video(video_path, "3840x2160", audio=True)
    media_id = _make_media(app, rel_path="2025/08/18/large.mp4", width=3840, height=2160)
    pb_id = _make_playback(app, media_id, "2025/08/18/large.mp4")

    with app.app_context():
        res = transcode_worker(media_playback_id=pb_id)
        assert res["ok"] is True
        from core.models.photo_models import MediaPlayback

        pb = MediaPlayback.query.get(pb_id)
        assert pb.width == 1920 and pb.height == 1080


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_worker_missing_audio(app):
    orig_dir = Path(os.environ["FPV_NAS_ORIG_DIR"])
    video_path = orig_dir / "2025/08/18/noaudio.mp4"
    _make_video(video_path, "640x480", audio=False)
    media_id = _make_media(app, rel_path="2025/08/18/noaudio.mp4", width=640, height=480)
    pb_id = _make_playback(app, media_id, "2025/08/18/noaudio.mp4")

    with app.app_context():
        res = transcode_worker(media_playback_id=pb_id)
        assert res["ok"] is False
        from core.models.photo_models import MediaPlayback

        pb = MediaPlayback.query.get(pb_id)
        assert pb.status == "error"
        assert pb.error_msg == "missing_stream"


def test_worker_missing_input(app):
    media_id = _make_media(app, rel_path="2025/08/18/miss.mp4", width=640, height=480)
    pb_id = _make_playback(app, media_id, "2025/08/18/miss.mp4")
    with app.app_context():
        res = transcode_worker(media_playback_id=pb_id)
        assert res["ok"] is False
        from core.models.photo_models import MediaPlayback

        pb = MediaPlayback.query.get(pb_id)
        assert pb.status == "error"
        assert pb.error_msg == "missing_input"


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_worker_already_running(app):
    orig_dir = Path(os.environ["FPV_NAS_ORIG_DIR"])
    video_path = orig_dir / "2025/08/18/run.mp4"
    _make_video(video_path, "640x480", audio=True)
    media_id = _make_media(app, rel_path="2025/08/18/run.mp4", width=640, height=480)
    pb_id = _make_playback(app, media_id, "2025/08/18/run.mp4", status="processing")
    with app.app_context():
        res = transcode_worker(media_playback_id=pb_id)
        assert res["ok"] is False
        assert res["note"] == "already_running"
