"""インポート処理のテンプレートメソッド実装."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Mapping, MutableMapping, Optional

from ...domain.importing.import_session import ImportSession
from .commands import ImportCommand
from .logging import ImportEventLoggerAdapter
from .results import ImportResult


class AbstractImporter(ABC):
    """共通フローを定義するテンプレートメソッド基底クラス."""

    def __init__(self, *, logger, event_logger=None) -> None:
        self._logger = logger
        self._event_logger = ImportEventLoggerAdapter(event_logger or logger)

    def execute(self, command: ImportCommand) -> ImportResult:
        result = self._create_result(command)
        session = self._create_session(command, result)
        self._emit_event(
            "info",
            "import.session.created",
            "Import session created",
            command=command,
            session=session,
            result=result,
        )
        try:
            self._emit_event(
                "info",
                "import.stage.pre_process.start",
                "Preparing import session",
                command=command,
                session=session,
                result=result,
                status=session.status,
                details={"stage": "pre_process"},
            )
            self._pre_process(command, session, result)
            self._emit_event(
                "info",
                "import.stage.pre_process.complete",
                "Pre-process completed",
                command=command,
                session=session,
                result=result,
                status=session.status,
                details={"stage": "pre_process"},
            )

            self._emit_event(
                "info",
                "import.stage.fetch.start",
                "Fetching sources",
                command=command,
                session=session,
                result=result,
                status=session.status,
                details={"stage": "fetch"},
            )
            sources = self._fetch_sources(command, session, result)
            self._emit_event(
                "info",
                "import.stage.fetch.complete",
                "Source discovery completed",
                command=command,
                session=session,
                result=result,
                status=session.status,
                details={"stage": "fetch", "source_type": type(sources).__name__},
            )

            self._emit_event(
                "info",
                "import.stage.normalize.start",
                "Normalizing sources",
                command=command,
                session=session,
                result=result,
                status=session.status,
                details={"stage": "normalize"},
            )
            normalized = self._normalize_sources(sources, command, session, result)
            self._emit_event(
                "info",
                "import.stage.normalize.complete",
                "Normalization completed",
                command=command,
                session=session,
                result=result,
                status=session.status,
                details={"stage": "normalize", "normalized_type": type(normalized).__name__},
            )

            self._emit_event(
                "info",
                "import.stage.register.start",
                "Registering media",
                command=command,
                session=session,
                result=result,
                status=session.status,
                details={"stage": "register"},
            )
            self._register_media(normalized, command, session, result)
            self._emit_event(
                "info",
                "import.stage.register.complete",
                "Media registration completed",
                command=command,
                session=session,
                result=result,
                status=session.status,
                details={"stage": "register"},
            )

            self._emit_event(
                "info",
                "import.stage.post_process.start",
                "Running post-process hooks",
                command=command,
                session=session,
                result=result,
                status=session.status,
                details={"stage": "post_process"},
            )
            self._post_process(command, session, result)
            self._emit_event(
                "info",
                "import.stage.post_process.complete",
                "Post-process completed",
                command=command,
                session=session,
                result=result,
                status=session.status,
                details={"stage": "post_process"},
            )
        except Exception as exc:
            message = str(exc)
            result.add_error(message)
            session.mark_failed(message)
            self._emit_event(
                "error",
                "import.session.failed",
                "Import session failed",
                command=command,
                session=session,
                result=result,
                status=session.status,
                exc_info=True,
                details={"stage": "failed", "error": message, "error_type": type(exc).__name__},
            )
            self._on_failure(exc, command, session, result)
        else:
            session.mark_completed()
            self._emit_event(
                "info",
                "import.session.completed",
                "Import session completed",
                command=command,
                session=session,
                result=result,
                status=session.status,
            )
        return result

    def _create_result(self, command: ImportCommand) -> ImportResult:
        return ImportResult()

    @abstractmethod
    def _create_session(self, command: ImportCommand, result: ImportResult) -> ImportSession:
        ...

    def _pre_process(self, command: ImportCommand, session: ImportSession, result: ImportResult) -> None:
        session.mark_running()
        self._logger.info(
            "import.start",
            extra={"session": session.to_dict(), "source": command.source},
        )
        self._emit_event(
            "info",
            "import.session.started",
            "Import session started",
            command=command,
            session=session,
            result=result,
            status=session.status,
            details={"stage": "pre_process"},
        )

    @abstractmethod
    def _fetch_sources(
        self,
        command: ImportCommand,
        session: ImportSession,
        result: ImportResult,
    ) -> Iterable:
        ...

    @abstractmethod
    def _normalize_sources(
        self,
        sources: Iterable,
        command: ImportCommand,
        session: ImportSession,
        result: ImportResult,
    ) -> Iterable:
        ...

    @abstractmethod
    def _register_media(
        self,
        normalized: Iterable,
        command: ImportCommand,
        session: ImportSession,
        result: ImportResult,
    ) -> None:
        ...

    def _post_process(
        self,
        command: ImportCommand,
        session: ImportSession,
        result: ImportResult,
    ) -> None:
        self._logger.info(
            "import.complete",
            extra={
                "session": session.to_dict(),
                "result": result.to_dict(),
            },
        )
        self._emit_event(
            "info",
            "import.session.summary",
            "Import post-process completed",
            command=command,
            session=session,
            result=result,
            status=session.status,
            details={"stage": "post_process"},
        )

    def _on_failure(
        self,
        exc: Exception,
        command: ImportCommand,
        session: ImportSession,
        result: ImportResult,
    ) -> None:
        self._logger.exception(
            "import.failed",
            extra={
                "session": session.to_dict(),
                "result": result.to_dict(),
                "error": type(exc).__name__,
            },
        )

    def _emit_event(
        self,
        level: str,
        event: str,
        message: str,
        *,
        command: Optional[ImportCommand] = None,
        session: Optional[ImportSession] = None,
        result: Optional[ImportResult] = None,
        status: Optional[str] = None,
        exc_info: bool = False,
        details: Optional[Mapping[str, object]] = None,
    ) -> None:
        if not hasattr(self, "_event_logger") or self._event_logger is None:
            return

        payload: MutableMapping[str, object] = {}

        if session is not None:
            payload["session_id"] = session.session_id
            payload["session_status"] = session.status
        elif result is not None and result.session_id:
            payload["session_id"] = result.session_id

        if command is not None:
            payload["import_source"] = command.source
            if command.account_id is not None:
                payload["account_id"] = command.account_id

        if result is not None:
            payload["imported_count"] = result.imported_count
            payload["skipped_count"] = result.skipped_count
            payload["duplicates_count"] = result.duplicates_count
            if result.errors:
                payload["errors"] = list(result.errors)

        if details:
            for key, value in details.items():
                if value is not None:
                    payload[key] = value

        resolved_status = status or (session.status if session else None)
        self._event_logger.emit(
            level,
            event,
            message,
            status=resolved_status,
            payload=payload,
            exc_info=exc_info,
        )


__all__ = ["AbstractImporter"]
