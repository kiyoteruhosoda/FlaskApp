"""Google フォト取り込み戦略（将来拡張用のスタブ）。"""
from __future__ import annotations

from typing import Iterable, List

from features.photonest.domain.importing import ImportSession, Media, MediaFactory
from features.photonest.domain.importing.services import ImportDomainService
from features.photonest.infrastructure.importing.google import (
    GoogleMediaClient,
    GoogleMediaItem,
)

from ..commands import ImportCommand
from ..results import ImportResult
from ..template import AbstractImporter


class GoogleImporter(AbstractImporter):
    """Google フォトからの取り込み戦略."""

    def __init__(
        self,
        *,
        client: GoogleMediaClient,
        media_factory: MediaFactory,
        domain_service: ImportDomainService,
        logger,
    ) -> None:
        super().__init__(logger=logger)
        self._client = client
        self._media_factory = media_factory
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
    ) -> Iterable[GoogleMediaItem]:
        assert command.account_id  # policy で保証済み
        return self._client.list_media(command.account_id)

    def _normalize_sources(
        self,
        sources: Iterable[GoogleMediaItem],
        command: ImportCommand,
        session: ImportSession,
        result: ImportResult,
    ) -> Iterable[Media]:
        medias: List[Media] = []
        for item in sources:
            try:
                media = self._media_factory.create_from_google_media(
                    item,
                    extras={
                        "account_id": command.account_id,
                    },
                )
            except Exception as exc:
                result.add_error(f"解析失敗: {item.id}: {exc}")
                result.mark_skipped()
                continue
            medias.append(media)
        return medias

    def _register_media(
        self,
        normalized: Iterable[Media],
        command: ImportCommand,
        session: ImportSession,
        result: ImportResult,
    ) -> None:
        for media in normalized:
            try:
                status = self._domain_service.register_media(session, media)
            except Exception as exc:
                result.add_error(f"登録失敗: {media.filename}: {exc}")
                result.mark_skipped()
                continue

            if status == "duplicate":
                result.mark_duplicate()
            elif status == "imported":
                result.mark_imported()
            else:
                result.mark_skipped()


__all__ = ["GoogleImporter"]
