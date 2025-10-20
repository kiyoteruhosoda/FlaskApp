"""Tests for logging configuration helpers."""

import json
import logging
from typing import Any

import pytest

import core.db_log_handler as db_log_handler_module

from core import logging_config
from core.db_log_handler import DBLogHandler, WorkerDBLogHandler
from core.logging_config import ensure_appdb_file_logging, setup_task_logging


@pytest.fixture
def cleanup_logger():
    loggers = []

    def _register(name: str) -> logging.Logger:
        logger = logging.getLogger(name)
        loggers.append(logger)
        return logger

    yield _register

    for logger in loggers:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.NOTSET)


def _flush_handlers(logger: logging.Logger) -> None:
    for handler in logger.handlers:
        flush = getattr(handler, "flush", None)
        if callable(flush):
            flush()


def test_ensure_appdb_logging_uses_database_handler(monkeypatch, cleanup_logger):
    records = []

    class DummyHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - simple data push
            records.append(record)

    dummy_handler = DummyHandler()
    setattr(dummy_handler, "_is_appdb_log_handler", True)

    monkeypatch.setattr(logging_config, "_create_appdb_db_handler", lambda: dummy_handler)

    logger = cleanup_logger("test.ensure_appdb")
    logger.propagate = False

    ensure_appdb_file_logging(logger)

    logger.info("progress message", extra={"event": "test.progress"})
    _flush_handlers(logger)

    assert dummy_handler in logger.handlers
    assert records and records[0].getMessage() == "progress message"


def test_setup_task_logging_uses_worker_handler(monkeypatch, cleanup_logger):
    records = []

    class DummyHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - simple data push
            records.append(record)

    dummy_handler = DummyHandler()
    setattr(dummy_handler, "_is_worker_db_log_handler", True)

    monkeypatch.setattr(logging_config, "_create_worker_db_handler", lambda: dummy_handler)

    logger_name = "core.tasks.test_logger"
    logger = cleanup_logger(logger_name)
    logger.propagate = False

    configured = setup_task_logging(logger_name)
    assert configured is logger

    logger.info("task finished", extra={"event": "test.task"})
    _flush_handlers(logger)

    assert dummy_handler in logger.handlers
    assert records and records[0].getMessage() == "task finished"


def test_setup_task_logging_removes_appdb_handler(monkeypatch, cleanup_logger):
    worker_handler = WorkerDBLogHandler()
    setattr(worker_handler, "_is_worker_db_log_handler", True)

    monkeypatch.setattr(logging_config, "_create_worker_db_handler", lambda: worker_handler)

    logger_name = "core.tasks.cleanup_logger"
    logger = cleanup_logger(logger_name)
    logger.propagate = False

    legacy_handler = DBLogHandler()
    setattr(legacy_handler, "_is_appdb_log_handler", True)
    logger.addHandler(legacy_handler)

    setup_task_logging(logger_name)

    assert worker_handler in logger.handlers
    assert legacy_handler not in logger.handlers


def test_ensure_appdb_logging_marks_existing_handler(monkeypatch, cleanup_logger):
    def fail_create():  # pragma: no cover - we ensure it's never called
        raise AssertionError("Should not create a new handler when one already exists")

    monkeypatch.setattr(logging_config, "_create_appdb_db_handler", fail_create)

    logger = cleanup_logger("test.ensure_appdb.reuse")
    logger.propagate = False

    existing_handler = DBLogHandler()
    logger.addHandler(existing_handler)

    ensure_appdb_file_logging(logger)

    assert getattr(existing_handler, "_is_appdb_log_handler", False)
    assert logger.level == logging.INFO


def test_worker_handler_extracts_fields_from_payload():
    handler = WorkerDBLogHandler()
    record = logging.LogRecord(
        name="celery.task",
        level=logging.INFO,
        pathname=__file__,
        lineno=123,
        msg="",
        args=(),
        exc_info=None,
    )

    payload = {
        "message": "Task finished",
        "task_name": "app.tasks.example",
        "task_uuid": "123e4567-e89b-12d3-a456-426614174000",
        "worker_hostname": "worker@example",
        "queue_name": "celery",
        "status": "SUCCESS",
        "_meta": {"foo": "bar"},
        "_extra": {"baz": "qux"},
    }

    result = handler._build_insert_values(
        record=record,
        message_json=json.dumps(payload, ensure_ascii=False),
        trace=None,
        event="celery_task",
        path_value=None,
        request_id=None,
        payload=payload,
        extras={},
    )

    assert result["task_name"] == "app.tasks.example"
    assert result["task_uuid"] == "123e4567-e89b-12d3-a456-426614174000"
    assert result["worker_hostname"] == "worker@example"
    assert result["queue_name"] == "celery"
    assert result["status"] == "SUCCESS"
    assert result["meta_json"] == {"foo": "bar"}
    assert result["extra_json"] == {"baz": "qux"}

    message_payload = json.loads(result["message"])
    assert message_payload["task_name"] == "app.tasks.example"
    assert message_payload["task_uuid"] == "123e4567-e89b-12d3-a456-426614174000"
    assert message_payload["worker_hostname"] == "worker@example"
    assert message_payload["queue_name"] == "celery"
    # Ensure other fields remain untouched.
    assert message_payload["message"] == "Task finished"
    assert message_payload["status"] == "SUCCESS"


def test_db_log_handler_uses_custom_trace(monkeypatch):
    captured: dict[str, Any] = {}

    class DummyInsert:
        def __init__(self, model):  # pragma: no cover - simple carrier
            self.model = model
            self.values_data = None

        def values(self, **kwargs):
            self.values_data = kwargs
            return self

    def fake_insert(model):  # pragma: no cover - deterministic stub
        dummy = DummyInsert(model)
        captured["insert"] = dummy
        return dummy

    class FakeConnection:
        def execute(self, stmt):  # pragma: no cover - capture execution
            captured["executed_stmt"] = stmt

    class FakeContext:
        def __enter__(self):  # pragma: no cover - simple context
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb):  # pragma: no cover - no suppression
            return False

    class FakeEngine:
        def begin(self):  # pragma: no cover - emulate engine
            return FakeContext()

    class DummyTable:
        def create(self, bind, checkfirst):  # pragma: no cover - no-op for tests
            captured["table_checked"] = True

    class DummyModel:
        __table__ = DummyTable()

    handler = DBLogHandler()

    monkeypatch.setattr(handler, "_resolve_engine", lambda: FakeEngine())
    monkeypatch.setattr(handler, "_ensure_table", lambda engine: None)
    monkeypatch.setattr(handler, "_get_log_model", lambda: DummyModel)
    monkeypatch.setattr(db_log_handler_module, "insert", fake_insert)

    record = logging.LogRecord(
        name="test.logger",
        level=logging.WARNING,
        pathname=__file__,
        lineno=321,
        msg=json.dumps({"message": "problem"}),
        args=(),
        exc_info=None,
    )
    record.trace = "decoded jwt payload"

    handler.emit(record)

    dummy_insert = captured.get("insert")
    assert dummy_insert is not None
    assert dummy_insert.values_data["trace"] == "decoded jwt payload"

    persisted_payload = json.loads(dummy_insert.values_data["message"])
    assert "_extra" not in persisted_payload or "trace" not in persisted_payload.get("_extra", {})
