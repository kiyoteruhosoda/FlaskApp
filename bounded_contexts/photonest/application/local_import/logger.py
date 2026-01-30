"""ローカルインポートタスク用のロギングユーティリティ."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union

from core.logging_config import log_task_error, log_task_info
from bounded_contexts.photonest.domain.local_import.logging import LogEntry


def compose_message(
    message: str,
    payload: Dict[str, Any],
    status: Optional[str],
) -> Tuple[str, Dict[str, Any], str]:
    """Build structured log information for task logging compatibility."""

    details = dict(payload)
    session_id = details.pop("session_id", None)
    entry_status = details.pop("status", None)

    entry = LogEntry(
        message=message,
        details=details,
        session_id=session_id,
        status=entry_status,
    )
    default_status = status or entry_status or "info"
    return entry.compose(default_status)


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


_UNSET = object()


@dataclass(frozen=True)
class ImportLogContext:
    """ローカル／Google 取り込みで共有するログコンテキスト."""

    session_id: Optional[str] = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def bind(
        self,
        *,
        session_id: Any = _UNSET,
        payload: Optional[Mapping[str, Any]] = None,
    ) -> "ImportLogContext":
        """追加情報を適用した新しいコンテキストを返す."""

        new_session_id = self.session_id if session_id is _UNSET else session_id
        merged_payload: Dict[str, Any] = dict(self.payload)
        if payload:
            merged_payload.update(payload)
        return ImportLogContext(session_id=new_session_id, payload=merged_payload)


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
        payload: Dict[str, Any] = dict(details)
        if session_id is not None:
            payload.setdefault("session_id", session_id)
        composed: Union[str, Tuple[str, Dict[str, Any], str]] = compose_message(
            message,
            payload,
            status or severity.default_status,
        )

        if isinstance(composed, tuple):
            composed_message, payload, resolved_status = composed
        else:
            composed_message = composed
            resolved_status = status or severity.default_status
            payload = dict(payload)

        payload_for_log = dict(payload)
        payload_for_log.pop("status", None)

        severity.log_to_task(
            self._task_logger,
            composed_message,
            event=event,
            status=resolved_status,
            payload=payload_for_log,
            exc_info=exc_info,
        )
        severity.log_to_celery(
            self._celery_logger,
            composed_message,
            event=event,
            status=resolved_status,
            payload=payload_for_log,
            exc_info=exc_info,
        )


class ImportLogEmitter:
    """LocalImportTaskLogger を共通利用するためのアダプタ."""

    def __init__(
        self,
        task_logger: LocalImportTaskLogger,
        *,
        normalise_event: Callable[[str], str],
        context: Optional[ImportLogContext] = None,
    ) -> None:
        self._task_logger = task_logger
        self._normalise_event = normalise_event
        self._context = context or ImportLogContext()

    def bind(self, *, session_id=_UNSET, **payload: Any) -> "ImportLogEmitter":
        """コンテキストを追加適用した新しいエミッタを生成."""

        bound_context = self._context.bind(
            session_id=session_id,
            payload=payload if payload else None,
        )
        return ImportLogEmitter(
            self._task_logger,
            normalise_event=self._normalise_event,
            context=bound_context,
        )

    def info(self, event: str, message: str, *, session_id=_UNSET, status: Optional[str] = None, **details: Any) -> None:
        self._emit("info", event, message, session_id=session_id, status=status, **details)

    def warning(self, event: str, message: str, *, session_id=_UNSET, status: Optional[str] = None, **details: Any) -> None:
        self._emit("warning", event, message, session_id=session_id, status=status, **details)

    def error(
        self,
        event: str,
        message: str,
        *,
        session_id=_UNSET,
        status: Optional[str] = None,
        exc_info: bool = False,
        **details: Any,
    ) -> None:
        self._emit(
            "error",
            event,
            message,
            session_id=session_id,
            status=status,
            exc_info=exc_info,
            **details,
        )

    def _emit(
        self,
        level: str,
        event: str,
        message: str,
        *,
        session_id,
        status: Optional[str],
        exc_info: bool = False,
        **details: Any,
    ) -> None:
        context = self._context
        resolved_session_id = context.session_id if session_id is _UNSET else session_id
        payload: Dict[str, Any] = dict(context.payload)
        payload.update(details)

        normalised_event = self._normalise_event(event)

        if level == "info":
            self._task_logger.info(
                normalised_event,
                message,
                session_id=resolved_session_id,
                status=status,
                **payload,
            )
        elif level == "warning":
            self._task_logger.warning(
                normalised_event,
                message,
                session_id=resolved_session_id,
                status=status,
                **payload,
            )
        else:
            self._task_logger.error(
                normalised_event,
                message,
                session_id=resolved_session_id,
                status=status,
                exc_info=exc_info,
                **payload,
            )
