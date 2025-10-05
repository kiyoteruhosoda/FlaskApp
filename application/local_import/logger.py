"""ローカルインポートタスク用のロギングユーティリティ."""
from __future__ import annotations

from typing import Any, Optional

from core.logging_config import log_task_error, log_task_info
from domain.local_import.logging import compose_message, with_session


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
        payload = with_session(details, session_id)
        resolved_status = status if status is not None else "info"
        composed = compose_message(message, payload, resolved_status)

        log_task_info(
            self._task_logger,
            composed,
            event=event,
            status=resolved_status,
            **payload,
        )
        self._celery_logger.info(
            composed,
            extra={"event": event, "status": resolved_status, **payload},
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
        payload = with_session(details, session_id)
        resolved_status = status if status is not None else "warning"
        composed = compose_message(message, payload, resolved_status)

        self._task_logger.warning(
            composed,
            extra={"event": event, "status": resolved_status, **payload},
        )
        self._celery_logger.warning(
            composed,
            extra={"event": event, "status": resolved_status, **payload},
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
        payload = with_session(details, session_id)
        resolved_status = status if status is not None else "error"
        composed = compose_message(message, payload, resolved_status)

        log_task_error(
            self._task_logger,
            composed,
            event=event,
            status=resolved_status,
            exc_info=exc_info,
            **payload,
        )
        self._celery_logger.error(
            composed,
            extra={"event": event, "status": resolved_status, **payload},
            exc_info=exc_info,
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
