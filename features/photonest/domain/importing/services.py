"""インポートドメインサービス."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

from .import_session import ImportSession
from .media import Media
from .media_hash import MediaHash


class MediaRepository(Protocol):
    """メディア永続化のためのリポジトリ抽象."""

    def exists_by_hash(self, media_hash: MediaHash) -> bool:
        ...

    def save_media(self, media: Media, session: ImportSession) -> None:
        ...


class HasherAdapter(Protocol):
    """pHash 計算のためのアダプタ抽象."""

    def normalize(self, media: Media) -> Media:
        ...


@dataclass(slots=True)
class ImportDomainService:
    """重複判定や正規化を担うドメインサービス."""

    media_repository: MediaRepository
    hasher: HasherAdapter

    def register_media(self, session: ImportSession, media: Media) -> str:
        """メディアを正規化し保存する。結果種別を返却。"""

        normalized = self.hasher.normalize(media)
        if self.media_repository.exists_by_hash(normalized.hash):
            return "duplicate"

        self.media_repository.save_media(normalized, session)
        return "imported"


__all__ = ["ImportDomainService", "MediaRepository", "HasherAdapter"]
