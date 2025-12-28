import os
import base64
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from core.tasks import (
    backfill_playback_posters,
    transcode_queue_scan,
    transcode_worker,
)
from core.tasks import transcode as transcode_module


ffmpeg_missing = shutil.which("ffmpeg") is None


@pytest.fixture
def app(tmp_path):
    """Create an application with temporary directories and database."""
    db_path = tmp_path / "test.db"
    orig = tmp_path / "orig"
    play = tmp_path / "play"
    thumbs = tmp_path / "thumbs"
    tmpd = tmp_path / "tmp"
    orig.mkdir()
    play.mkdir()
    thumbs.mkdir()
    tmpd.mkdir()

    env_keys = {
        "SECRET_KEY": "test",
        "DATABASE_URI": f"sqlite:///{db_path}",
        "MEDIA_ORIGINALS_DIRECTORY": str(orig),
        "MEDIA_PLAYBACK_DIRECTORY": str(play),
        "MEDIA_THUMBNAILS_DIRECTORY": str(thumbs),
        "MEDIA_TEMP_DIRECTORY": str(tmpd),
        "MEDIA_DOWNLOAD_SIGNING_KEY": base64.urlsafe_b64encode(b"1" * 32).decode(),
    }
    prev_env = {k: os.environ.get(k) for k in env_keys}
    os.environ.update(env_keys)

    import importlib, sys
    import webapp.config as config_module
    importlib.reload(config_module)
    import webapp as webapp_module
    importlib.reload(webapp_module)
    from webapp.config import BaseApplicationSettings
    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
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
            source_type='local',
            google_media_id=None,
            account_id=None,
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
    orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
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
    orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
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
    orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
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
        assert pb.poster_rel_path is not None
        m = Media.query.get(media_id)
        assert m.has_playback is True
        assert m.thumbnail_rel_path is not None
        out = Path(os.environ["MEDIA_PLAYBACK_DIRECTORY"]) / pb.rel_path
        assert res["output_path"] == str(out)
        assert out.exists()
        poster = Path(os.environ["MEDIA_PLAYBACK_DIRECTORY"]) / pb.poster_rel_path
        assert res["poster_path"] == str(poster)
        assert poster.exists()
        thumb_path = Path(os.environ["MEDIA_THUMBNAILS_DIRECTORY"]) / "256" / m.thumbnail_rel_path
        assert thumb_path.exists()


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_worker_transcode_passthrough_mp4(app):
    orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
    video_path = orig_dir / "2025/08/18/passthrough.mp4"
    _make_video(video_path, "1280x720", audio=True)
    media_id = _make_media(app, rel_path="2025/08/18/passthrough.mp4", width=1280, height=720)
    pb_id = _make_playback(app, media_id, "2025/08/18/passthrough.mp4")

    with app.app_context():
        res = transcode_worker(media_playback_id=pb_id)
        assert res["ok"] is True
        assert res["note"] == "passthrough"
        from core.models.photo_models import MediaPlayback, Media

        pb = MediaPlayback.query.get(pb_id)
        assert pb is not None
        assert pb.status == "done"
        play_path = Path(os.environ["MEDIA_PLAYBACK_DIRECTORY"]) / pb.rel_path
        assert res["output_path"] == str(play_path)
        assert play_path.exists()
        assert play_path.read_bytes() == video_path.read_bytes()
        media = Media.query.get(media_id)
        assert media and media.has_playback is True


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_worker_transcode_detects_missing_output(app, monkeypatch):
    orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
    video_path = orig_dir / "2025/08/18/missing_output.mp4"
    _make_video(video_path, "640x360", audio=True)
    media_id = _make_media(app, rel_path="2025/08/18/missing_output.mp4", width=640, height=360)
    pb_id = _make_playback(app, media_id, "2025/08/18/missing_output.mp4")

    original_move = shutil.move

    def fake_move(src, dest):
        original_move(src, dest)
        Path(dest).unlink(missing_ok=True)

    monkeypatch.setattr(shutil, "move", fake_move)

    with app.app_context():
        res = transcode_worker(media_playback_id=pb_id)
        assert res["ok"] is False
        assert res["note"] == "missing_output"

        from core.models.photo_models import MediaPlayback, Media

        pb = MediaPlayback.query.get(pb_id)
        assert pb.status == "error"
        assert pb.error_msg == "missing_output"

        media = Media.query.get(media_id)
        assert media.has_playback is False


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_worker_transcode_normalizes_rel_path(app):
    orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
    video_path = orig_dir / "2025/08/18/win.mov"
    _make_video(video_path, "640x360", audio=True)
    media_id = _make_media(app, rel_path="2025/08/18/win.mov", width=640, height=360)

    with app.app_context():
        from webapp.extensions import db
        from core.models.photo_models import MediaPlayback

        pb = MediaPlayback(
            media_id=media_id,
            preset="std1080p",
            rel_path=r"2025\\08\\18\\win.MOV",
            status="pending",
        )
        db.session.add(pb)
        db.session.commit()

        pb_id = pb.id
        res = transcode_worker(media_playback_id=pb_id)
        assert res["ok"] is True

        db.session.refresh(pb)
        assert pb.rel_path == "2025/08/18/win.mp4"
        assert "\\" not in pb.rel_path
        assert pb.poster_rel_path is not None
        assert "\\" not in pb.poster_rel_path
        play_path = Path(os.environ["MEDIA_PLAYBACK_DIRECTORY"]) / pb.rel_path
        assert play_path.exists()


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_worker_transcode_media_detail_playback(app):
    orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
    video_path = orig_dir / "2025/08/18/detail.mov"
    _make_video(video_path, "1280x720", audio=True)
    media_id = _make_media(app, rel_path="2025/08/18/detail.mov", width=1280, height=720)
    pb_id = _make_playback(app, media_id, "2025/08/18/detail.mov")

    with app.app_context():
        res = transcode_worker(media_playback_id=pb_id)
        assert res["ok"] is True

    app.config["LOGIN_DISABLED"] = True
    client = app.test_client()

    res = client.post(f"/api/media/{media_id}/playback-url")
    assert res.status_code == 200
    data = res.get_json()
    assert data and "url" in data

    playback_url = data["url"]
    res2 = client.get(playback_url)
    assert res2.status_code == 200
    assert res2.headers.get("Content-Type") == "video/mp4"
    content_length = int(res2.headers.get("Content-Length", "0"))
    assert content_length > 0
    assert len(res2.data) == content_length


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_worker_transcode_populates_playback_metadata(app):
    orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
    video_path = orig_dir / "2025/08/18/meta.mov"
    _make_video(video_path, "640x360", audio=True)
    media_id = _make_media(
        app,
        rel_path="2025/08/18/meta.mov",
        width=640,
        height=360,
        duration_ms=1500,
    )
    pb_id = _make_playback(app, media_id, "2025/08/18/meta.mov")

    with app.app_context():
        res = transcode_worker(media_playback_id=pb_id)
        assert res["ok"] is True

        from core.models.photo_models import MediaPlayback

        pb = MediaPlayback.query.get(pb_id)
        assert pb is not None
        assert pb.rel_path.endswith(".mp4")
        assert pb.width == 640
        assert pb.height == 360
        assert pb.duration_ms is not None and pb.duration_ms > 0
        assert pb.v_codec
        assert pb.a_codec
        assert pb.v_bitrate_kbps is None or pb.v_bitrate_kbps > 0


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_backfill_playback_posters_existing_playback(app):
    orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
    video_path = orig_dir / "2025/08/18/backfill.mp4"
    _make_video(video_path, "640x480", audio=True)
    media_id = _make_media(app, rel_path="2025/08/18/backfill.mp4", width=640, height=480)
    pb_id = _make_playback(app, media_id, "2025/08/18/backfill.mp4")

    with app.app_context():
        transcode_worker(media_playback_id=pb_id)

        from core.models.photo_models import MediaPlayback, Media
        from webapp.extensions import db

        pb = MediaPlayback.query.get(pb_id)
        m = Media.query.get(media_id)
        assert pb.poster_rel_path is not None
        assert m.thumbnail_rel_path is not None

        play_dir = Path(os.environ["MEDIA_PLAYBACK_DIRECTORY"])
        thumbs_dir = Path(os.environ["MEDIA_THUMBNAILS_DIRECTORY"])
        poster_path = play_dir / pb.poster_rel_path
        poster_path.unlink()
        old_thumb_rel = m.thumbnail_rel_path
        for size in ("256", "512", "1024", "2048"):
            thumb_path = thumbs_dir / size / old_thumb_rel
            thumb_path.unlink(missing_ok=True)

        pb.poster_rel_path = None
        m.thumbnail_rel_path = None
        db.session.commit()

        res = backfill_playback_posters()
        assert res["processed"] >= 1
        assert res["updated"] >= 1

        db.session.refresh(pb)
        db.session.refresh(m)

        assert pb.poster_rel_path is not None
        assert (play_dir / pb.poster_rel_path).exists()
        assert m.thumbnail_rel_path is not None
        thumb_256 = thumbs_dir / "256" / m.thumbnail_rel_path
        assert thumb_256.exists()


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_worker_transcode_downscale(app):
    orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
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
    orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
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


def test_summarise_ffmpeg_error_prefers_width_issue() -> None:
    sample = "\n".join(
        [
            "Some banner",
            "[libx264 @ 0xabc] width not divisible by 2 (809x1080)",
            "[vost#0:0/libx264 @ 0xdef] Error while opening encoder - maybe incorrect parameters such as bit_rate, rate, width or height.",
            "Conversion failed!",
        ]
    )

    summary = transcode_module._summarise_ffmpeg_error(sample)
    assert summary == "[libx264 @ 0xabc] width not divisible by 2 (809x1080)"


def test_worker_returns_error_summary_on_ffmpeg_failure(app, monkeypatch):
    orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
    video_path = orig_dir / "2025/08/18/badwidth.mov"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"fake")

    media_id = _make_media(app, rel_path="2025/08/18/badwidth.mov", width=640, height=480)
    pb_id = _make_playback(app, media_id, "2025/08/18/badwidth.mov")

    fake_probe_result = {
        "streams": [
            {"codec_type": "video", "codec_name": "hevc", "width": 640, "height": 480},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
        "format": {"duration": "1.0", "bit_rate": "1000"},
    }

    monkeypatch.setattr(transcode_module, "_probe", lambda path: fake_probe_result)

    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if cmd and cmd[0] == "ffmpeg" and "-vf" in cmd:
            stderr = "\n".join(
                [
                    "[libx264 @ 0xabc] width not divisible by 2 (809x1080)",
                    "[vost#0:0/libx264 @ 0xdef] Error while opening encoder - maybe incorrect parameters such as bit_rate, rate, width or height.",
                    "Conversion failed!",
                ]
            )
            return SimpleNamespace(returncode=187, stderr=stderr, stdout="")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with app.app_context():
        res = transcode_worker(media_playback_id=pb_id)

    assert res["ok"] is False
    assert res["note"] == "ffmpeg_error"
    assert "width not divisible" in res["error"]


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
    orig_dir = Path(os.environ["MEDIA_ORIGINALS_DIRECTORY"])
    video_path = orig_dir / "2025/08/18/run.mp4"
    _make_video(video_path, "640x480", audio=True)
    media_id = _make_media(app, rel_path="2025/08/18/run.mp4", width=640, height=480)
    pb_id = _make_playback(app, media_id, "2025/08/18/run.mp4", status="processing")
    with app.app_context():
        res = transcode_worker(media_playback_id=pb_id)
        assert res["ok"] is False
        assert res["note"] == "already_running"
