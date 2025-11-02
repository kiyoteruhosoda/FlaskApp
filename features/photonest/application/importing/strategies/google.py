"""Google フォト取り込み戦略（将来拡張用のスタブ）。"""
from __future__ import annotations

from typing import Iterable

from features.photonest.domain.importing import ImportSession
from features.photonest.domain.importing.services import ImportDomainService
from features.photonest.infrastructure.importing.google import GoogleMediaClient

from ..commands import ImportCommand
from ..results import ImportResult
from ..template import AbstractImporter


class GoogleImporter(AbstractImporter):
    """Google フォトからの取り込み戦略."""

    def __init__(
        self,
        *,
        client: GoogleMediaClient,
        domain_service: ImportDomainService,
        logger,
    ) -> None:
        super().__init__(logger=logger)
        self._client = client
        self._domain_service = domain_service

    def _create_session(self, command: ImportCommand, result: ImportResult) -> ImportSession:
        session_id = command.option("session_id") or f"google-{command.account_id}"
        result.session_id = session_id
        return ImportSession(session_id=session_id, source=command.source)

    def _fetch_sources(
        self,
        command: ImportCommand,
        session: ImportSession,
        result: ImportResult,
    ) -> Iterable:
        assert command.account_id  # policy で保証済み
        return self._client.list_media(command.account_id)

    def _normalize_sources(
        self,
        sources: Iterable,
        command: ImportCommand,
        session: ImportSession,
        result: ImportResult,
    ) -> Iterable:
        # Google 側はまだ実装されていないため、そのまま返却
        return sources

    def _register_media(
        self,
        normalized: Iterable,
        command: ImportCommand,
        session: ImportSession,
        result: ImportResult,
    ) -> None:
        for _ in normalized:
            result.mark_skipped()
            result.add_error("Google インポートは未実装です")


__all__ = ["GoogleImporter"]
