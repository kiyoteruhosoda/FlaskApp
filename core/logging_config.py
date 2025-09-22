"""Logging configuration for core tasks."""

from __future__ import annotations

import logging
import os
from logging.handlers import WatchedFileHandler
from pathlib import Path
from typing import Optional

from flask import current_app, has_app_context


_APPDB_HANDLER_ATTR = "_is_appdb_log_handler"
_APPDB_LOG_ENV = "APP_DB_LOG_PATH"
_APPDB_DEFAULT_FILENAME = "appdb.log"


def _resolve_appdb_log_path() -> Path:
    """Return filesystem path for the appdb log file."""

    env_path = os.environ.get(_APPDB_LOG_ENV)
    if env_path:
        path = Path(env_path)
    else:
        path = Path(_APPDB_DEFAULT_FILENAME)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _create_appdb_file_handler() -> logging.Handler:
    """Create a file handler for appdb.log with sane defaults."""

    log_path = _resolve_appdb_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = WatchedFileHandler(log_path)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    setattr(handler, _APPDB_HANDLER_ATTR, True)
    return handler


def ensure_appdb_file_logging(logger: logging.Logger) -> None:
    """Attach the appdb.log file handler to *logger* if missing."""

    for handler in logger.handlers:
        if getattr(handler, _APPDB_HANDLER_ATTR, False):
            break
    else:
        file_handler = _create_appdb_file_handler()
        logger.addHandler(file_handler)

    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)


def setup_task_logging(logger_name: Optional[str] = None) -> logging.Logger:
    """Setup logging for core tasks to use DBLogHandler and appdb.log."""

    from core.db_log_handler import DBLogHandler

    # Get logger
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()

    # Check if DBLogHandler is already added
    if not any(isinstance(h, DBLogHandler) for h in logger.handlers):
        app_obj = current_app._get_current_object() if has_app_context() else None
        db_handler = DBLogHandler(app=app_obj)
        db_handler.setLevel(logging.INFO)
        logger.addHandler(db_handler)

    ensure_appdb_file_logging(logger)

    return logger


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
