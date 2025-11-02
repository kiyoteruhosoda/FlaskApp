"""ローカル取り込み戦略."""
from __future__ import annotations

import uuid
from typing import Iterable, List

from features.photonest.domain.importing import MediaFactory, ImportSession, Media
from features.photonest.domain.importing.services import ImportDomainService
from features.photonest.infrastructure.importing.files import LocalFileRepository

from ..commands import ImportCommand
from ..results import ImportResult
from ..template import AbstractImporter


class LocalImporter(AbstractImporter):
    """ローカルファイルシステムからの取り込み戦略."""

    def __init__(
        self,
        *,
        file_repository: LocalFileRepository,
        media_factory: MediaFactory,
        domain_service: ImportDomainService,
        logger,
    ) -> None:
        super().__init__(logger=logger)
        self._file_repository = file_repository
        self._media_factory = media_factory
        self._domain_service = domain_service

    def _create_session(self, command: ImportCommand, result: ImportResult) -> ImportSession:
        session_id = command.option("session_id") or f"local-{uuid.uuid4().hex}"
        result.session_id = session_id
        return ImportSession(session_id=session_id, source=command.source)

    def _fetch_sources(
        self,
        command: ImportCommand,
        session: ImportSession,
        result: ImportResult,
    ) -> Iterable[str]:
        assert command.directory_path  # policy で保証済み
        files = self._file_repository.list_media(command.directory_path)
        if not files:
            result.add_error("取り込み対象ファイルが見つかりません")
        return files

    def _normalize_sources(
        self,
        sources: Iterable[str],
        command: ImportCommand,
        session: ImportSession,
        result: ImportResult,
    ) -> Iterable[Media]:
        medias: List[Media] = []
        for path in sources:
            try:
                media = self._media_factory.create_from_path(
                    path,
                    origin="local",
                    extras={
                        "account_id": command.account_id,
                        "original_path": path,
                    },
                )
            except Exception as exc:
                result.add_error(f"解析失敗: {path}: {exc}")
                result.mark_skipped()
                continue
            medias.append(media)
        return medias

    def _register_media(
        self,
        normalized: Iterable,
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


__all__ = ["LocalImporter"]
