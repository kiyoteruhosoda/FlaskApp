"""Album ユースケースの入力コマンド（DTO）.

Presentation 層がリクエストから組み立て、Application 層へ渡す。
「キーが存在しない（更新対象外）」と「値として null が来た」を区別するため、
未指定フィールドは :data:`UNSET` で表現する。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final


class _Unset:
    """「未指定」を表すシングルトン番兵."""

    _instance: "_Unset | None" = None

    def __new__(cls) -> "_Unset":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - 表示用
        return "UNSET"

    def __bool__(self) -> bool:
        return False


UNSET: Final[_Unset] = _Unset()


def is_set(value: Any) -> bool:
    """フィールドが明示的に指定されたかどうかを返す."""
    return value is not UNSET


@dataclass(frozen=True)
class CreateAlbumCommand:
    """アルバム作成の入力."""

    name: Any = None
    description: Any = None
    visibility: Any = None
    media_ids: Any = None
    cover_media_id: Any = UNSET


@dataclass(frozen=True)
class UpdateAlbumCommand:
    """アルバム更新の入力（部分更新）.

    未指定フィールドは :data:`UNSET`。``cover_media_id`` は「キーが存在したか」を
    区別する必要があるため、キー不在時のみ :data:`UNSET` とする。
    """

    album_id: int
    name: Any = UNSET
    description: Any = UNSET
    visibility: Any = UNSET
    media_ids: Any = UNSET
    cover_media_id: Any = UNSET


@dataclass(frozen=True)
class ReorderAlbumMediaCommand:
    """アルバム内メディアの並べ替え入力."""

    album_id: int
    media_ids: Any = None


@dataclass(frozen=True)
class ReorderAlbumsCommand:
    """アルバム自体の表示順並べ替え入力."""

    album_ids: Any = None


__all__ = [
    "UNSET",
    "is_set",
    "CreateAlbumCommand",
    "UpdateAlbumCommand",
    "ReorderAlbumMediaCommand",
    "ReorderAlbumsCommand",
]
