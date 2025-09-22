"""Tests for logging configuration helpers."""

import logging

import pytest

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


def test_ensure_appdb_file_logging_writes_progress(tmp_path, monkeypatch, cleanup_logger):
    log_path = tmp_path / "appdb.log"
    monkeypatch.setenv("APP_DB_LOG_PATH", str(log_path))

    logger = cleanup_logger("test.ensure_appdb")
    logger.propagate = False

    ensure_appdb_file_logging(logger)

    logger.info("progress message", extra={"event": "test.progress"})
    _flush_handlers(logger)

    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "progress message" in content
    assert any(getattr(h, "_is_appdb_log_handler", False) for h in logger.handlers)


def test_setup_task_logging_includes_appdb_handler(tmp_path, monkeypatch, cleanup_logger):
    log_path = tmp_path / "custom_appdb.log"
    db_path = tmp_path / "log.db"
    monkeypatch.setenv("APP_DB_LOG_PATH", str(log_path))
    monkeypatch.setenv("DATABASE_URI", f"sqlite:///{db_path}")

    logger_name = "core.tasks.test_logger"
    logger = cleanup_logger(logger_name)
    logger.propagate = False

    configured = setup_task_logging(logger_name)
    assert configured is logger

    logger.info("task finished", extra={"event": "test.task"})
    _flush_handlers(logger)

    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "task finished" in content
    assert any(getattr(h, "_is_appdb_log_handler", False) for h in logger.handlers)
