"""Logging configuration for core tasks."""

from __future__ import annotations

import logging
import os
from typing import Optional

from flask import current_app, has_app_context


_APPDB_HANDLER_ATTR = "_is_appdb_log_handler"


def _create_appdb_db_handler() -> logging.Handler:
    """Create a DBLogHandler configured for appdb logging."""

    from core.db_log_handler import DBLogHandler

    app_obj = current_app._get_current_object() if has_app_context() else None
    handler = DBLogHandler(app=app_obj)
    handler.setLevel(logging.INFO)
    setattr(handler, _APPDB_HANDLER_ATTR, True)
    return handler


def ensure_appdb_file_logging(logger: logging.Logger) -> None:
    """Attach the database-backed appdb log handler to *logger* if missing."""

    testing_env = os.environ.get("TESTING", "").strip().lower()

    if testing_env in {"1", "true", "yes", "on"}:
        if logger.level == logging.NOTSET:
            logger.setLevel(logging.INFO)
        return

    if has_app_context():
        app = current_app._get_current_object()
        if app.config.get("TESTING"):
            if logger.level == logging.NOTSET:
                logger.setLevel(logging.INFO)
            return

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


def setup_task_logging(logger_name: Optional[str] = None) -> logging.Logger:
    """Setup logging for core tasks to use the database-backed appdb handler."""

    # Get logger
    if logger_name:
        logger = logging.getLogger(logger_name)
    else:
        logger = logging.getLogger()

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
