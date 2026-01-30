from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest
from PIL import Image
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace


TEST_RETRY_BLOCKERS = {"reason": "playback assets pending"}


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
        "MEDIA_ORIGINALS_DIRECTORY": str(orig),
        "MEDIA_PLAYBACK_DIRECTORY": str(play),
        "MEDIA_THUMBNAILS_DIRECTORY": str(thumbs),
    }
    prev_env = {k: os.environ.get(k) for k in env_keys}
    os.environ.update(env_keys)

    import webapp.config as config_module
    import webapp as webapp_module

    importlib.reload(config_module)
    importlib.reload(webapp_module)

    from webapp.config import BaseApplicationSettings

    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}

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

    play_dir = Path(os.environ["MEDIA_PLAYBACK_DIRECTORY"])
    thumbs_dir = Path(os.environ["MEDIA_THUMBNAILS_DIRECTORY"])

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
        expected_output = (play_dir / playback.rel_path).as_posix()
        expected_poster = (play_dir / poster_rel).as_posix()
        assert result["output_path"] == expected_output
        assert result["poster_path"] == expected_poster
        assert "thumbnails" in result
        assert result["thumbnails"].get("ok") is True

        db.session.refresh(media)
        assert media.thumbnail_rel_path == "2025/09/27/video.jpg"

    thumb_path = thumbs_dir / "256" / "2025/09/27/video.jpg"
    assert thumb_path.exists()


def test_enqueue_thumbs_generate_schedules_retry(monkeypatch):
    """サムネイル生成が保留の場合に再試行がスケジュールされることを確認。"""

    from bounded_contexts.photonest.application.media_processing.retry_service import RetryScheduleResult
    from core.tasks import media_post_processing

    monkeypatch.setattr(
        media_post_processing,
        "thumbs_generate",
        lambda media_id, force=False: {
            "ok": True,
            "generated": [],
            "skipped": [256, 512, 1024, 2048],
            "notes": media_post_processing.PLAYBACK_NOT_READY_NOTES,
            "paths": {},
            "retry_blockers": dict(TEST_RETRY_BLOCKERS),
        },
    )

    scheduled: dict = {}

    class StubRetryService:
        def schedule_if_allowed(self, **kwargs):
            scheduled.update(kwargs)
            return RetryScheduleResult(
                scheduled=True,
                countdown=media_post_processing._THUMBNAIL_RETRY_COUNTDOWN,
                celery_task_id="fake-task",
                attempts=1,
                max_attempts=media_post_processing._THUMBNAIL_RETRY_MAX_ATTEMPTS,
                blockers=kwargs.get("blockers"),
            )

        def clear_success(self, media_id: int) -> None:  # pragma: no cover - 呼ばれない
            pass

    monkeypatch.setattr(media_post_processing, "_build_retry_service", lambda logger: StubRetryService())

    result = media_post_processing.enqueue_thumbs_generate(123, force=True)

    assert result["retry_scheduled"] is True
    assert result["retry_details"] == {
        "scheduled": True,
        "countdown": media_post_processing._THUMBNAIL_RETRY_COUNTDOWN,
        "celery_task_id": "fake-task",
        "attempts": 1,
        "max_attempts": media_post_processing._THUMBNAIL_RETRY_MAX_ATTEMPTS,
        "blockers": dict(TEST_RETRY_BLOCKERS),
    }
    assert scheduled["media_id"] == 123
    assert scheduled["force"] is True
    assert scheduled["blockers"] == dict(TEST_RETRY_BLOCKERS)


@pytest.mark.usefixtures("app")
def test_enqueue_thumbs_generate_records_retry(app, monkeypatch):
    from core.tasks import media_post_processing
    from webapp.extensions import db
    from core.models.photo_models import Media
    from core.models.celery_task import CeleryTaskRecord, CeleryTaskStatus
    import cli.src.celery.tasks as celery_tasks

    monkeypatch.setattr(
        media_post_processing,
        "thumbs_generate",
        lambda media_id, force=False: {
            "ok": True,
            "generated": [],
            "skipped": [256, 512, 1024, 2048],
            "notes": media_post_processing.PLAYBACK_NOT_READY_NOTES,
            "paths": {},
            "retry_blockers": dict(TEST_RETRY_BLOCKERS),
        },
    )

    def fake_apply_async(*args, **kwargs):
        return SimpleNamespace(id="fake-task-id")

    monkeypatch.setattr(celery_tasks.thumbs_generate_task, "apply_async", fake_apply_async)

    with app.app_context():
        media = Media(
            source_type="local",
            local_rel_path="2025/09/27/video.mp4",
            filename="video.mp4",
            hash_sha256="0" * 64,
            bytes=1024,
            mime_type="video/mp4",
            width=1280,
            height=720,
            duration_ms=1000,
            is_video=True,
            has_playback=True,
            shot_at=datetime(2025, 9, 27, tzinfo=timezone.utc),
            imported_at=datetime(2025, 9, 27, tzinfo=timezone.utc),
        )
        db.session.add(media)
        db.session.commit()

        result = media_post_processing.enqueue_thumbs_generate(media.id, force=True)

        assert result["retry_scheduled"] is True
        assert result["retry_details"]["attempts"] == 1
        assert (
            result["retry_details"]["max_attempts"]
            == media_post_processing._THUMBNAIL_RETRY_MAX_ATTEMPTS
        )
        assert result["retry_details"]["blockers"] == dict(TEST_RETRY_BLOCKERS)
        retry = (
            CeleryTaskRecord.query.filter_by(
                task_name=media_post_processing._THUMBNAIL_RETRY_TASK_NAME,
                object_type="media",
                object_id=str(media.id),
            )
            .order_by(CeleryTaskRecord.id.desc())
            .one()
        )
        assert retry.status == CeleryTaskStatus.SCHEDULED
        assert retry.payload.get("force") is True
        assert retry.payload.get("attempts") == 1
        assert retry.payload.get("blockers") == dict(TEST_RETRY_BLOCKERS)
        assert retry.celery_task_id == "fake-task-id"
        retry_at = retry.scheduled_for
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        remaining = retry_at - datetime.now(timezone.utc)
        assert remaining.total_seconds() > 0
        assert remaining <= timedelta(seconds=media_post_processing._THUMBNAIL_RETRY_COUNTDOWN + 5)


@pytest.mark.usefixtures("app")
def test_process_due_thumbnail_retries_clears_success(app, monkeypatch):
    from core.tasks import media_post_processing
    from webapp.extensions import db
    from core.models.photo_models import Media
    from core.models.celery_task import CeleryTaskRecord, CeleryTaskStatus

    monkeypatch.setattr(
        media_post_processing,
        "thumbs_generate",
        lambda media_id, force=False: {
            "ok": True,
            "generated": [256],
            "skipped": [],
            "notes": None,
            "paths": {256: "/tmp/thumb.jpg"},
        },
    )

    with app.app_context():
        media = Media(
            source_type="local",
            local_rel_path="2025/09/27/video.mp4",
            filename="video.mp4",
            hash_sha256="1" * 64,
            bytes=2048,
            mime_type="video/mp4",
            width=1920,
            height=1080,
            duration_ms=2000,
            is_video=True,
            has_playback=True,
            shot_at=datetime(2025, 9, 27, tzinfo=timezone.utc),
            imported_at=datetime(2025, 9, 27, tzinfo=timezone.utc),
        )
        db.session.add(media)
        db.session.commit()

        retry = CeleryTaskRecord(
            task_name=media_post_processing._THUMBNAIL_RETRY_TASK_NAME,
            object_type="media",
            object_id=str(media.id),
            status=CeleryTaskStatus.SCHEDULED,
            scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
            celery_task_id="existing",
        )
        retry.update_payload({"force": True})
        db.session.add(retry)
        db.session.commit()

        summary = media_post_processing.process_due_thumbnail_retries(limit=5)

        assert summary == {
            "processed": 1,
            "rescheduled": 0,
            "cleared": 1,
            "pending_before": 1,
        }
        remaining = CeleryTaskRecord.query.filter_by(
            task_name=media_post_processing._THUMBNAIL_RETRY_TASK_NAME,
            object_type="media",
            object_id=str(media.id),
        ).one()
        assert remaining.status == CeleryTaskStatus.SUCCESS
        assert remaining.scheduled_for is None
        assert remaining.payload == {}


@pytest.mark.usefixtures("app")
def test_process_due_thumbnail_retries_reschedules_pending(app, monkeypatch):
    from core.tasks import media_post_processing
    from webapp.extensions import db
    from core.models.photo_models import Media
    from core.models.celery_task import CeleryTaskRecord, CeleryTaskStatus
    import cli.src.celery.tasks as celery_tasks

    monkeypatch.setattr(
        media_post_processing,
        "thumbs_generate",
        lambda media_id, force=False: {
            "ok": True,
            "generated": [],
            "skipped": [256, 512, 1024, 2048],
            "notes": media_post_processing.PLAYBACK_NOT_READY_NOTES,
            "paths": {},
            "retry_blockers": dict(TEST_RETRY_BLOCKERS),
        },
    )

    def fake_apply_async(*args, **kwargs):
        return SimpleNamespace(id="retry-task")

    monkeypatch.setattr(celery_tasks.thumbs_generate_task, "apply_async", fake_apply_async)

    with app.app_context():
        media = Media(
            source_type="local",
            local_rel_path="2025/09/28/video.mp4",
            filename="video.mp4",
            hash_sha256="2" * 64,
            bytes=4096,
            mime_type="video/mp4",
            width=1920,
            height=1080,
            duration_ms=3000,
            is_video=True,
            has_playback=True,
            shot_at=datetime(2025, 9, 28, tzinfo=timezone.utc),
            imported_at=datetime(2025, 9, 28, tzinfo=timezone.utc),
        )
        db.session.add(media)
        db.session.commit()

        retry = CeleryTaskRecord(
            task_name=media_post_processing._THUMBNAIL_RETRY_TASK_NAME,
            object_type="media",
            object_id=str(media.id),
            status=CeleryTaskStatus.SCHEDULED,
            scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        retry.update_payload({"force": False})
        db.session.add(retry)
        db.session.commit()

        previous_retry_at = retry.scheduled_for

        summary = media_post_processing.process_due_thumbnail_retries(limit=5)

        assert summary == {
            "processed": 1,
            "rescheduled": 1,
            "cleared": 0,
            "pending_before": 1,
        }

        updated = (
            CeleryTaskRecord.query.filter_by(
                task_name=media_post_processing._THUMBNAIL_RETRY_TASK_NAME,
                object_type="media",
                object_id=str(media.id),
            )
            .order_by(CeleryTaskRecord.id.desc())
            .one()
        )
        assert updated.scheduled_for > previous_retry_at
        assert updated.celery_task_id == "retry-task"
        assert updated.payload.get("force") is False
        assert updated.payload.get("attempts") == 1
        assert updated.payload.get("blockers") == dict(TEST_RETRY_BLOCKERS)


@pytest.mark.usefixtures("app")
def test_process_due_thumbnail_retries_reports_blocked_retries(app, monkeypatch):
    from core.tasks import media_post_processing
    from webapp.extensions import db
    from core.models.celery_task import CeleryTaskRecord, CeleryTaskStatus

    class StubLogger:
        def __init__(self):
            self.warnings = []

        def info(self, **kwargs):  # pragma: no cover - not relevant here
            pass

        def warning(self, **kwargs):
            self.warnings.append(kwargs)

        def error(self, **kwargs):  # pragma: no cover - not used
            pass

    stub_logger = StubLogger()
    monkeypatch.setattr(media_post_processing, "_build_structured_logger", lambda logger_override=None: stub_logger)

    with app.app_context():
        retry = CeleryTaskRecord(
            task_name=media_post_processing._THUMBNAIL_RETRY_TASK_NAME,
            object_type="media",
            object_id="123",
            status=CeleryTaskStatus.FAILED,
        )
        retry.update_payload(
            {
                "attempts": media_post_processing._THUMBNAIL_RETRY_MAX_ATTEMPTS,
                "retry_disabled": True,
                "blockers": {"reason": "completed playback missing"},
            }
        )
        db.session.add(retry)
        db.session.commit()

        summary = media_post_processing.process_due_thumbnail_retries(limit=5)

        assert summary == {
            "processed": 0,
            "rescheduled": 0,
            "cleared": 0,
            "pending_before": 0,
        }

        assert stub_logger.warnings
        last_log = stub_logger.warnings[-1]
        assert last_log["event"] == "thumbnail_generation.retry_monitor_blocked"
        assert last_log["disabled"] == 1
        assert str(last_log["samples"][0]["media_id"]) == "123"
        assert last_log["samples"][0]["blockers"] == {
            "reason": "completed playback missing"
        }

        refreshed = db.session.get(CeleryTaskRecord, retry.id)
        assert refreshed.payload.get("monitor_reported") is True


@pytest.mark.usefixtures("app")
def test_enqueue_thumbs_generate_stops_after_max_attempts(app, monkeypatch):
    from core.tasks import media_post_processing
    from webapp.extensions import db
    from core.models.photo_models import Media
    from core.models.celery_task import CeleryTaskRecord, CeleryTaskStatus

    monkeypatch.setattr(
        media_post_processing,
        "thumbs_generate",
        lambda media_id, force=False: {
            "ok": True,
            "generated": [],
            "skipped": [256, 512, 1024, 2048],
            "notes": media_post_processing.PLAYBACK_NOT_READY_NOTES,
            "paths": {},
            "retry_blockers": dict(TEST_RETRY_BLOCKERS),
        },
    )

    with app.app_context():
        media = Media(
            source_type="local",
            local_rel_path="2025/09/29/video.mp4",
            filename="video.mp4",
            hash_sha256="3" * 64,
            bytes=1024,
            mime_type="video/mp4",
            width=1280,
            height=720,
            duration_ms=1500,
            is_video=True,
            has_playback=True,
            shot_at=datetime(2025, 9, 29, tzinfo=timezone.utc),
            imported_at=datetime(2025, 9, 29, tzinfo=timezone.utc),
        )
        db.session.add(media)
        db.session.commit()

        retry = CeleryTaskRecord(
            task_name=media_post_processing._THUMBNAIL_RETRY_TASK_NAME,
            object_type="media",
            object_id=str(media.id),
            status=CeleryTaskStatus.SCHEDULED,
            scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        retry.update_payload(
            {
                "force": False,
                "attempts": media_post_processing._THUMBNAIL_RETRY_MAX_ATTEMPTS,
            }
        )
        db.session.add(retry)
        db.session.commit()

        result = media_post_processing.enqueue_thumbs_generate(media.id)

        assert "retry_scheduled" not in result
        assert result["retry_details"]["reason"] == "max_attempts"
        assert result["retry_details"]["blockers"] == dict(TEST_RETRY_BLOCKERS)
        assert (
            result["retry_details"]["attempts"]
            == media_post_processing._THUMBNAIL_RETRY_MAX_ATTEMPTS
        )
        assert result["retry_details"]["scheduled"] is False

        stored = (
            CeleryTaskRecord.query.filter_by(
                task_name=media_post_processing._THUMBNAIL_RETRY_TASK_NAME,
                object_type="media",
                object_id=str(media.id),
            )
            .order_by(CeleryTaskRecord.id.desc())
            .one()
        )
        assert stored.status == CeleryTaskStatus.FAILED
        assert stored.scheduled_for is None
        assert stored.payload.get("attempts") == media_post_processing._THUMBNAIL_RETRY_MAX_ATTEMPTS
        assert stored.payload.get("retry_disabled") is True
        assert stored.payload.get("blockers") == dict(TEST_RETRY_BLOCKERS)

