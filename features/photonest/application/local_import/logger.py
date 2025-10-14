"""ローカルインポートタスク用のロギングユーティリティ."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Tuple

from core.logging_config import log_task_error, log_task_info
from features.photonest.domain.local_import.logging import LogEntry


class _LogSeverity(Enum):
    """Celery タスクで利用するログレベル。"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    @property
    def default_status(self) -> str:
        return self.value

    def log_to_task(
        self,
        task_logger,
        message: str,
        *,
        event: str,
        status: str,
        payload: Dict[str, Any],
        exc_info: bool,
    ) -> None:
        extra = {"event": event, "status": status, **payload}
        if self is _LogSeverity.INFO:
            log_task_info(task_logger, message, event=event, status=status, **payload)
        elif self is _LogSeverity.WARNING:
            task_logger.warning(message, extra=extra)
        else:
            log_task_error(
                task_logger,
                message,
                event=event,
                status=status,
                exc_info=exc_info,
                **payload,
            )

    def log_to_celery(
        self,
        celery_logger,
        message: str,
        *,
        event: str,
        status: str,
        payload: Dict[str, Any],
        exc_info: bool,
    ) -> None:
        extra = {"event": event, "status": status, **payload}
        if self is _LogSeverity.INFO:
            celery_logger.info(message, extra=extra)
        elif self is _LogSeverity.WARNING:
            celery_logger.warning(message, extra=extra)
        else:
            celery_logger.error(message, extra=extra, exc_info=exc_info)


class LocalImportTaskLogger:
    """Celery タスク向けのロガーをまとめて扱うヘルパ."""

    def __init__(self, task_logger, celery_logger) -> None:  # pragma: no cover - 型ヒント用
        self._task_logger = task_logger
        self._celery_logger = celery_logger

    def info(
        self,
        event: str,
        message: str,
        *,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
        **details: Any,
    ) -> None:
        self._log(
            _LogSeverity.INFO,
            event,
            message,
            session_id=session_id,
            status=status,
            exc_info=False,
            details=details,
        )

    def warning(
        self,
        event: str,
        message: str,
        *,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
        **details: Any,
    ) -> None:
        self._log(
            _LogSeverity.WARNING,
            event,
            message,
            session_id=session_id,
            status=status,
            exc_info=False,
            details=details,
        )

    def error(
        self,
        event: str,
        message: str,
        *,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
        exc_info: bool = False,
        **details: Any,
    ) -> None:
        self._log(
            _LogSeverity.ERROR,
            event,
            message,
            session_id=session_id,
            status=status,
            exc_info=exc_info,
            details=details,
        )

    def commit_with_error_logging(
        self,
        db,
        event: str,
        message: str,
        *,
        session_id: Optional[str] = None,
        celery_task_id: Optional[str] = None,
        exc_info: bool = True,
        **details: Any,
    ) -> None:
        """``db.session.commit()`` を実行し、失敗時にはエラーログを出す."""

        try:
            db.session.commit()
        except Exception as exc:  # pragma: no cover - 例外経路の網羅が困難
            try:
                db.session.rollback()
            except Exception:  # pragma: no cover - ロールバック失敗はログのみ
                pass

            self.error(
                event,
                message,
                session_id=session_id,
                celery_task_id=celery_task_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
                exc_info=exc_info,
                **details,
            )
            raise

    def _log(
        self,
        severity: _LogSeverity,
        event: str,
        message: str,
        *,
        session_id: Optional[str],
        status: Optional[str],
        exc_info: bool,
        details: Dict[str, Any],
    ) -> None:
        entry = LogEntry(message=message, details=details, session_id=session_id, status=status)
        composed_message, payload, resolved_status = entry.compose(severity.default_status)

        severity.log_to_task(
            self._task_logger,
            composed_message,
            event=event,
            status=resolved_status,
            payload=payload,
            exc_info=exc_info,
        )
        severity.log_to_celery(
            self._celery_logger,
            composed_message,
            event=event,
            status=resolved_status,
            payload=payload,
            exc_info=exc_info,
        )
