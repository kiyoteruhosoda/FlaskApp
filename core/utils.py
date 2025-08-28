"""Utility helpers for the application."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from flask import current_app


def greet(name: str) -> str:
    """Return a friendly greeting."""
    return f"Hello {name}"


def log_status_change(obj: Any, old: str | None, new: str) -> None:
    """Log a status transition for ``obj``.

    Parameters
    ----------
    obj:
        The model instance whose status changed.  Its class name and ``id``
        attribute (if present) are recorded.
    old:
        Previous status value.  May be ``None`` if unknown.
    new:
        New status value.
    """

    logger = getattr(current_app, "logger", logging.getLogger(__name__))
    logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "model": obj.__class__.__name__,
                "id": getattr(obj, "id", None),
                "from": old,
                "to": new,
            },
            ensure_ascii=False,
        ),
        extra={"event": "status.change"},
    )
