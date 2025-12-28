"""Logging configuration for core tasks."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional, cast

from flask import current_app, has_app_context


_APPDB_HANDLER_ATTR = "_is_appdb_log_handler"
_WORKER_HANDLER_ATTR = "_is_worker_db_log_handler"


if TYPE_CHECKING:  # pragma: no cover
    from flask import Flask


def _resolve_flask_app() -> Optional["Flask"]:
    """Return the concrete Flask app when an application context is active."""

    if not has_app_context():
        return None

    getter = getattr(current_app, "_get_current_object", None)
    if callable(getter):
        return cast("Flask", getter())
    return cast("Flask", current_app)


def _create_appdb_db_handler() -> logging.Handler:
    """Create a DBLogHandler configured for appdb logging."""

    from core.db_log_handler import DBLogHandler

    app_obj = _resolve_flask_app()
    handler = DBLogHandler(app=app_obj)
    handler.setLevel(logging.INFO)
    setattr(handler, _APPDB_HANDLER_ATTR, True)
    return handler


def ensure_appdb_file_logging(logger: logging.Logger) -> None:
    """Attach the database-backed appdb log handler to *logger* if missing."""

    from core.db_log_handler import DBLogHandler

    for handler in logger.handlers:
        if getattr(handler, _APPDB_HANDLER_ATTR, False):
            break
        if isinstance(handler, DBLogHandler):
            setattr(handler, _APPDB_HANDLER_ATTR, True)
            break
    else:
        db_handler = _create_appdb_db_handler()
        logger.addHandler(db_handler)

    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)


def _create_worker_db_handler() -> logging.Handler:
    """Create a WorkerDBLogHandler configured for Celery worker logging."""

    from core.db_log_handler import WorkerDBLogHandler

    app_obj = _resolve_flask_app()
    handler = WorkerDBLogHandler(app=app_obj)
    handler.setLevel(logging.INFO)
    setattr(handler, _WORKER_HANDLER_ATTR, True)
    return handler


def ensure_worker_db_logging(logger: logging.Logger) -> None:
    """Attach the worker-specific database log handler to *logger* if missing."""

    from core.db_log_handler import DBLogHandler, WorkerDBLogHandler

    has_worker_handler = False

    for handler in list(logger.handlers):
        if isinstance(handler, WorkerDBLogHandler):
            has_worker_handler = True
            setattr(handler, _WORKER_HANDLER_ATTR, True)
        elif isinstance(handler, DBLogHandler) and getattr(handler, _APPDB_HANDLER_ATTR, False):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    if not has_worker_handler:
        worker_handler = _create_worker_db_handler()
        logger.addHandler(worker_handler)

    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)


def setup_task_logging(logger_name: Optional[str] = None) -> logging.Logger:
    """Setup logging for core tasks to use the worker database log handler."""

    # Get logger
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()

    ensure_worker_db_logging(logger)

    return logger


class StructuredTaskLogger:
    """Helper for emitting structured JSON logs for worker tasks."""

    def __init__(self, logger: logging.Logger, defaults: Optional[Mapping[str, Any]] = None):
        self._logger = logger
        self._defaults: Dict[str, Any] = dict(defaults or {})

    def bind(self, **extra: Any) -> "StructuredTaskLogger":
        """Return a new logger with additional default fields."""

        merged = dict(self._defaults)
        merged.update(extra)
        return StructuredTaskLogger(self._logger, merged)

    def _emit(self, level: int, event: str, **fields: Any) -> None:
        payload: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event": event,
            "level": logging.getLevelName(level),
        }
        payload.update(self._defaults)
        payload.update(fields)
        message = json.dumps(payload, ensure_ascii=False, default=str)
        self._logger.log(level, message)

    def log(self, level: int, event: str, **fields: Any) -> None:
        """Emit a log entry at *level* with structured payload."""

        self._emit(level, event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        self._emit(logging.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit(logging.WARNING, event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit(logging.ERROR, event, **fields)


def structured_task_logger(logger_name: str, **defaults: Any) -> StructuredTaskLogger:
    """Return a :class:`StructuredTaskLogger` with worker DB logging enabled."""

    logger = setup_task_logging(logger_name)
    return StructuredTaskLogger(logger, defaults)


def log_task_error(logger: logging.Logger, message: str, event: str, exc_info: bool = True, **extra_attrs):
    """Log task error with proper context for database storage.
    
    Args:
        logger: Logger instance to use.
        message: Error message.
        event: Event identifier for categorization.
        exc_info: Whether to include exception information.
        **extra_attrs: Additional attributes to include in log record.
    """
    extra = {
        'event': event,
        **extra_attrs
    }
    
    logger.error(message, exc_info=exc_info, extra=extra)


def log_task_info(logger: logging.Logger, message: str, event: str, **extra_attrs):
    """Log task info with proper context for database storage.
    
    Args:
        logger: Logger instance to use.
        message: Info message.
        event: Event identifier for categorization.
        **extra_attrs: Additional attributes to include in log record.
    """
    extra = {
        'event': event,
        **extra_attrs
    }
    
    logger.info(message, extra=extra)
