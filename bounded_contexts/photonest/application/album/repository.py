"""Album 集約のリポジトリ契約（インターフェース）.

Application 層はこの抽象にのみ依存する（DIP）。具体的な SQLAlchemy 実装は
Infrastructure 層に置く。永続化の集約ルートは ``Album`` エンティティ。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AlbumRepository(ABC):
    """Album 集約の永続化を抽象化する."""

    @abstractmethod
    def get(self, album_id: int) -> Any | None:
        """ID で 1 件取得する（存在しなければ ``None``）."""

    @abstractmethod
    def get_many(self, album_ids: list[int]) -> list[Any]:
        """複数 ID をまとめて取得する（順不同・存在するもののみ）."""

    @abstractmethod
    def add(self, album: Any) -> None:
        """新規アルバムを永続化対象に加える."""

    @abstractmethod
    def delete(self, album: Any) -> None:
        """アルバムを削除する."""

    @abstractmethod
    def load_ordered_media(self, media_ids: list[int]) -> tuple[list[Any], list[int]]:
        """指定 ID 順にメディアを取得し、(取得できたもの, 見つからなかったID) を返す."""

    @abstractmethod
    def replace_media(self, album: Any, ordered_media: list[Any]) -> None:
        """アルバムの収録メディアを差し替える（必要に応じて flush する）."""

    @abstractmethod
    def update_sort_indexes(self, album_id: int, media_ids: list[int]) -> None:
        """収録メディアの並び順（sort_index）を保存する."""

    @abstractmethod
    def media_rows(self, album_id: int) -> list[tuple[Any, int]]:
        """(Media, sort_index) を並び順で返す."""

    @abstractmethod
    def flush(self) -> None:
        """保留中の変更を DB へ送る（採番のため等）."""

    @abstractmethod
    def commit(self) -> None:
        """トランザクションを確定する."""

    @abstractmethod
    def rollback(self) -> None:
        """トランザクションを破棄する."""


__all__ = ["AlbumRepository"]
