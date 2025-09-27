"""Tests for logging configuration helpers."""

import logging

import pytest

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
