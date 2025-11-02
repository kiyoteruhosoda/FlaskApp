"""インポート処理のテンプレートメソッド実装."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from ...domain.importing.import_session import ImportSession
from .commands import ImportCommand
from .results import ImportResult


class AbstractImporter(ABC):
    """共通フローを定義するテンプレートメソッド基底クラス."""

    def __init__(self, *, logger) -> None:
        self._logger = logger

    def execute(self, command: ImportCommand) -> ImportResult:
        result = self._create_result(command)
        session = self._create_session(command, result)
        try:
            self._pre_process(command, session, result)
            sources = self._fetch_sources(command, session, result)
            normalized = self._normalize_sources(sources, command, session, result)
            self._register_media(normalized, command, session, result)
            self._post_process(command, session, result)
        except Exception as exc:
            result.add_error(str(exc))
            session.mark_failed(str(exc))
            self._on_failure(exc, command, session, result)
        else:
            session.mark_completed()
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


__all__ = ["AbstractImporter"]
