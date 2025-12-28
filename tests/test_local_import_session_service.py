from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import PendingRollbackError

from features.photonest.domain.local_import.session import LocalImportSessionService


class DummySession:
    def __init__(self) -> None:
        self.status = "pending"
        self.session_id = "local_import_test"
        self.id = 42
        self.last_progress_at = None
        self.updated_at = None
        self._stats: dict[str, object] = {}
        self.set_stats_calls = 0

    def stats(self) -> dict[str, object]:
        return dict(self._stats)

    def set_stats(self, data) -> None:  # type: ignore[no-untyped-def]
        self.set_stats_calls += 1
        self._stats = dict(data)


def _build_service(commit_side_effects=None):
    session_mock = MagicMock()
    if commit_side_effects is not None:
        session_mock.commit.side_effect = commit_side_effects
    db = SimpleNamespace(session=session_mock)
    logger = MagicMock()
    service = LocalImportSessionService(db, logger)
    return service, session_mock, logger


def test_set_progress_recovers_from_pending_rollback():
    service, db_session, logger = _build_service(
        commit_side_effects=[PendingRollbackError("pending"), None]
    )
    session = DummySession()

    service.set_progress(
        session,
        status="processing",
        stage="progress",
        celery_task_id="celery-1",
        stats_updates={"total": 1},
    )

    assert db_session.commit.call_count == 2
    db_session.rollback.assert_called_once()
    assert session.status == "processing"
    assert session._stats["total"] == 1
    assert session.set_stats_calls == 2
    logger.assert_any_call(
        "local_import.session.progress_retry",
        "無効なトランザクションをロールバックしてセッション更新を再試行",
        session_id=session.session_id,
        session_db_id=session.id,
        error_type="PendingRollbackError",
        error_message="pending",
    )


def test_set_progress_raises_when_retry_fails():
    service, db_session, logger = _build_service(
        commit_side_effects=[PendingRollbackError("pending"), RuntimeError("boom")]
    )
    session = DummySession()

    with pytest.raises(RuntimeError):
        service.set_progress(session)

    assert db_session.rollback.call_count == 2
    logger.assert_any_call(
        "local_import.session.progress_update_failed",
        "セッション状態の更新中にエラーが発生",
        session_id=session.session_id,
        session_db_id=session.id,
        error_type="RuntimeError",
        error_message="boom",
        exc_info=True,
    )
