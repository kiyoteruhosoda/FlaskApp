"""Import pipeline logging adapters."""
from __future__ import annotations

from typing import Any, Dict, Optional


class ImportEventLoggerAdapter:
    """Adapter that normalizes logging interfaces for import events."""

    def __init__(self, logger) -> None:  # pragma: no cover - simple assignment
        self._logger = logger
        self._is_task_logger = hasattr(logger, "commit_with_error_logging")

    def emit(
        self,
        level: str,
        event: str,
        message: str,
        *,
        status: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        exc_info: bool = False,
    ) -> None:
        payload = {key: value for key, value in (payload or {}).items() if value is not None}
        logger = getattr(self._logger, level, None)
        if logger is None:
            return

        if self._is_task_logger:
            call_kwargs: Dict[str, Any] = {}
            session_id = payload.pop("session_id", None)
            if session_id is not None:
                call_kwargs["session_id"] = session_id
            if status is not None:
                call_kwargs["status"] = status
            call_kwargs.update(payload)
            if level == "error":
                call_kwargs.setdefault("exc_info", exc_info)
            logger(event, message, **call_kwargs)
            return

        extra: Dict[str, Any] = {"event": event}
        if status is not None:
            extra["status"] = status
        extra.update(payload)
        logger(message, extra=extra, exc_info=exc_info)


__all__ = ["ImportEventLoggerAdapter"]
