import uuid
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("DATABASE_URI", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("ENCRYPTION_KEY", "a" * 32)
    monkeypatch.setenv("MEDIA_DOWNLOAD_SIGNING_KEY", "test-sign-key")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    from webapp import create_app

    app = create_app()

    with app.app_context():
        from core.db import db

        db.create_all()

    return app


def _make_time(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def test_cleanup_old_logs_removes_records(app):
    from core.db import db
    from core.models.job_sync import JobSync
    from core.models.log import Log
    from core.models.picker_session import PickerSession
    from core.models.worker_log import WorkerLog
    from core.tasks.log_cleanup import cleanup_old_logs

    with app.app_context():
        old_time = _make_time(400)
        recent_time = _make_time(100)

        old_log = Log(level="INFO", event="test", message="old", created_at=old_time)
        new_log = Log(level="INFO", event="test", message="new", created_at=recent_time)
        db.session.add_all([old_log, new_log])

        old_worker_log = WorkerLog(
            level="INFO",
            event="test",
            message="old worker",
            created_at=old_time,
        )
        new_worker_log = WorkerLog(
            level="INFO",
            event="test",
            message="new worker",
            created_at=recent_time,
        )
        db.session.add_all([old_worker_log, new_worker_log])

        old_session = PickerSession(
            session_id=f"picker_sessions/{uuid.uuid4()}",
            status="pending",
            created_at=old_time,
            updated_at=old_time,
        )
        protected_session = PickerSession(
            session_id=f"picker_sessions/{uuid.uuid4()}",
            status="pending",
            created_at=old_time,
            updated_at=old_time,
        )
        new_session = PickerSession(
            session_id=f"picker_sessions/{uuid.uuid4()}",
            status="pending",
            created_at=recent_time,
            updated_at=recent_time,
        )
        db.session.add_all([old_session, protected_session, new_session])
        db.session.flush()

        job_sync = JobSync(
            target="picker_import",
            task_name="test.task",
            trigger="worker",
            args_json="{}",
            stats_json="{}",
            started_at=recent_time,
            session_id=protected_session.id,
        )
        db.session.add(job_sync)
        db.session.commit()

        result = cleanup_old_logs(retention_days=365)

        assert result["ok"] is True
        assert result["deleted"]["log"] == 1
        assert result["deleted"]["worker_log"] == 1
        assert result["deleted"]["picker_session"] == 1

        remaining_log_messages = {log.message for log in Log.query.all()}
        assert remaining_log_messages == {"new"}

        remaining_worker_messages = {log.message for log in WorkerLog.query.all()}
        assert "old worker" not in remaining_worker_messages
        assert "new worker" in remaining_worker_messages

        remaining_sessions = PickerSession.query.all()
        remaining_session_ids = {session.session_id for session in remaining_sessions}
        assert protected_session.session_id in remaining_session_ids
        assert new_session.session_id in remaining_session_ids
        assert old_session.session_id not in remaining_session_ids
