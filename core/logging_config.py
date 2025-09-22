"""Logging configuration for core tasks."""

import logging
from typing import Optional

from flask import current_app, has_app_context


def setup_task_logging(logger_name: Optional[str] = None) -> logging.Logger:
    """Setup logging for core tasks to use DBLogHandler.
    
    Args:
        logger_name: Name of the logger. If None, uses root logger.
        
    Returns:
        Configured logger instance.
    """
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
        
        # Set logger level if not already set
        if logger.level == logging.NOTSET:
            logger.setLevel(logging.INFO)
    
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
