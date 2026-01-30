"""features.photonest.application.local_import.logger のテスト."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from bounded_contexts.photonest.application.local_import.logger import (
    ImportLogEmitter,
    LocalImportTaskLogger,
)
from bounded_contexts.photonest.domain.local_import.logging import compose_message, with_session


@pytest.fixture
def task_logger() -> MagicMock:
    return MagicMock()


@pytest.fixture
def celery_logger() -> MagicMock:
    return MagicMock()


def _expected_payload(**details: Any) -> Any:
    return with_session(details, "session")


def _expected_message(message: str, status: str, **details: Any) -> str:
    payload = _expected_payload(**details)
    return compose_message(message, payload, status)


def test_info_logs_to_task_and_celery(monkeypatch, task_logger, celery_logger) -> None:
    log_task_info = MagicMock()
    monkeypatch.setattr("features.photonest.application.local_import.logger.log_task_info", log_task_info)
    logger = LocalImportTaskLogger(task_logger, celery_logger)

    logger.info(
        "event",
        "message",
        session_id="session",
        user="alice",
    )

    payload = _expected_payload(user="alice")
    expected_message = _expected_message("message", "info", user="alice")

    log_task_info.assert_called_once_with(
        task_logger,
        expected_message,
        event="event",
        status="info",
        **payload,
    )
    celery_logger.info.assert_called_once_with(
        expected_message,
        extra={"event": "event", "status": "info", **payload},
    )


def test_warning_logs_with_custom_status(task_logger, celery_logger) -> None:
    logger = LocalImportTaskLogger(task_logger, celery_logger)

    logger.warning(
        "event",
        "message",
        session_id="session",
        status="custom",
        user="alice",
    )

    payload = _expected_payload(user="alice")
    expected_message = _expected_message("message", "custom", user="alice")

    task_logger.warning.assert_called_once_with(
        expected_message,
        extra={"event": "event", "status": "custom", **payload},
    )
    celery_logger.warning.assert_called_once_with(
        expected_message,
        extra={"event": "event", "status": "custom", **payload},
    )


def test_error_logs_and_propagates_exception(monkeypatch, task_logger, celery_logger) -> None:
    log_task_error = MagicMock()
    monkeypatch.setattr("features.photonest.application.local_import.logger.log_task_error", log_task_error)
    logger = LocalImportTaskLogger(task_logger, celery_logger)

    logger.error(
        "event",
        "message",
        session_id="session",
        exc_info=True,
        user="alice",
    )

    payload = _expected_payload(user="alice")
    expected_message = _expected_message("message", "error", user="alice")

    log_task_error.assert_called_once_with(
        task_logger,
        expected_message,
        event="event",
        status="error",
        exc_info=True,
        **payload,
    )
    celery_logger.error.assert_called_once_with(
        expected_message,
        extra={"event": "event", "status": "error", **payload},
        exc_info=True,
    )


def test_commit_with_error_logging_reports_and_reraises(monkeypatch, task_logger, celery_logger) -> None:
    log_task_error = MagicMock()
    monkeypatch.setattr("features.photonest.application.local_import.logger.log_task_error", log_task_error)
    logger = LocalImportTaskLogger(task_logger, celery_logger)

    class FailingSession:
        def commit(self) -> None:
            raise RuntimeError("boom")

        def rollback(self) -> None:
            pass

    db = SimpleNamespace(session=FailingSession())

    with pytest.raises(RuntimeError):
        logger.commit_with_error_logging(
            db,
            "event",
            "message",
            session_id="session",
            celery_task_id="celery-id",
        )

    payload = _expected_payload(celery_task_id="celery-id", error_type="RuntimeError", error_message="boom")
    expected_message = _expected_message(
        "message",
        "error",
        celery_task_id="celery-id",
        error_type="RuntimeError",
        error_message="boom",
    )

    log_task_error.assert_called_once_with(
        task_logger,
        expected_message,
        event="event",
        status="error",
        exc_info=True,
        **payload,
    )


def test_import_log_emitter_applies_context_and_normalisation() -> None:
    base_logger = MagicMock(spec=LocalImportTaskLogger)
    emitter = ImportLogEmitter(base_logger, normalise_event=lambda value: f"normalized.{value}")

    bound = emitter.bind(session_id="session-1", request_id="req-1")
    bound.info("event.start", "message", status="custom", attempt=1)

    base_logger.info.assert_called_once_with(
        "normalized.event.start",
        "message",
        session_id="session-1",
        status="custom",
        request_id="req-1",
        attempt=1,
    )


def test_import_log_emitter_merges_additional_context() -> None:
    base_logger = MagicMock(spec=LocalImportTaskLogger)
    emitter = ImportLogEmitter(base_logger, normalise_event=lambda value: value)

    base = emitter.bind(session_id="session-A", session_db_id=42)
    base.warning("event.warn", "warn", bytes=512)

    base_logger.warning.assert_called_once_with(
        "event.warn",
        "warn",
        session_id="session-A",
        status=None,
        session_db_id=42,
        bytes=512,
    )

    child = base.bind(session_id="session-B")
    child.error("event.fail", "error", exc_info=True, status="failed", retry=2)

    base_logger.error.assert_called_once_with(
        "event.fail",
        "error",
        session_id="session-B",
        status="failed",
        exc_info=True,
        session_db_id=42,
        retry=2,
    )
