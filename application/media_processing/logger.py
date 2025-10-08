"""メディア後処理用の構造化ロガー."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.logging_config import log_task_error, log_task_info


class StructuredMediaTaskLogger:
    """背景タスク向けの構造化ログ出力を担当する."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def info(
        self,
        *,
        event: str,
        message: str,
        operation_id: str,
        media_id: int,
        request_context: Optional[Dict[str, Any]] = None,
        **details: Any,
    ) -> None:
        self._log(
            level="info",
            event=event,
            message=message,
            operation_id=operation_id,
            media_id=media_id,
            request_context=request_context,
            details=details,
        )

    def warning(
        self,
        *,
        event: str,
        message: str,
        operation_id: str,
        media_id: int,
        request_context: Optional[Dict[str, Any]] = None,
        **details: Any,
    ) -> None:
        self._log(
            level="warning",
            event=event,
            message=message,
            operation_id=operation_id,
            media_id=media_id,
            request_context=request_context,
            details=details,
        )

    def error(
        self,
        *,
        event: str,
        message: str,
        operation_id: str,
        media_id: int,
        request_context: Optional[Dict[str, Any]] = None,
        exc_info: bool = False,
        **details: Any,
    ) -> None:
        self._log(
            level="error",
            event=event,
            message=message,
            operation_id=operation_id,
            media_id=media_id,
            request_context=request_context,
            details=details,
            exc_info=exc_info,
        )

    def _log(
        self,
        *,
        level: str,
        event: str,
        message: str,
        operation_id: str,
        media_id: int,
        request_context: Optional[Dict[str, Any]],
        details: Dict[str, Any],
        exc_info: bool = False,
    ) -> None:
        payload: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "level": level.upper(),
            "message": message,
            "operationId": operation_id,
            "mediaId": media_id,
        }
        if request_context:
            payload["requestContext"] = request_context
        if details:
            payload["details"] = details

        serialized = json.dumps(payload, ensure_ascii=False, default=str)
        log_kwargs = dict(details)
        log_kwargs.update({"event": event, "operation_id": operation_id, "media_id": media_id})

        level_lower = level.lower()
        if level_lower == "info":
            log_task_info(
                self._logger,
                serialized,
                event=event,
                operation_id=operation_id,
                media_id=media_id,
                **details,
            )
        elif level_lower == "warning":
            self._logger.warning(serialized, extra=log_kwargs)
        else:
            log_task_error(
                self._logger,
                serialized,
                event=event,
                operation_id=operation_id,
                media_id=media_id,
                exc_info=exc_info,
                **details,
            )
