"""Album 集約の値オブジェクトと不変条件.

ここに置くのは「値で等価・不変・副作用なし」のドメインロジックのみ。
DB やリクエスト形式（dict/JSON）には依存しない。
"""
from __future__ import annotations

from enum import Enum
from typing import Iterable

from .errors import (
    DuplicateMediaSelection,
    InvalidAlbumVisibility,
    InvalidMediaSelection,
)


class AlbumVisibility(str, Enum):
    """アルバムの公開範囲を表す値オブジェクト."""

    PUBLIC = "public"
    PRIVATE = "private"
    UNLISTED = "unlisted"

    @classmethod
    def values(cls) -> frozenset[str]:
        """許可される文字列値の集合を返す."""
        return frozenset(member.value for member in cls)

    @classmethod
    def parse(cls, raw: str | None) -> "AlbumVisibility":
        """文字列を正規化して ``AlbumVisibility`` に変換する.

        許可されない値の場合は :class:`InvalidAlbumVisibility` を送出する。
        """
        normalized = (raw or "").strip().lower()
        try:
            return cls(normalized)
        except ValueError as exc:  # 列挙にない値
            raise InvalidAlbumVisibility(normalized) from exc


def parse_media_ids(raw: object) -> list[int]:
    """作成・更新リクエストのメディア ID 配列を整形する（重複は黙って除去）.

    - ``None`` は空リスト
    - 各要素は整数へ変換（空文字・``None`` はスキップ）
    - 出現順を保ったまま重複を除去
    """
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise InvalidMediaSelection("mediaIds must be a list")

    ordered: list[int] = []
    seen: set[int] = set()
    for item in raw:
        if item in (None, ""):
            continue
        try:
            media_id = int(item)
        except (TypeError, ValueError) as exc:
            raise InvalidMediaSelection("mediaIds must contain integers") from exc
        if media_id not in seen:
            seen.add(media_id)
            ordered.append(media_id)
    return ordered


def parse_ordered_media_ids(raw: Iterable[object]) -> list[int]:
    """並べ替えリクエストのメディア ID を整形する（重複は許さない）.

    呼び出し側で ``raw`` がリストであることを保証すること。
    重複・非整数はいずれも不正な並び順として扱う。
    """
    ordered: list[int] = []
    seen: set[int] = set()
    for value in raw:
        try:
            media_id = int(value)
        except (TypeError, ValueError) as exc:
            raise InvalidMediaSelection("media order must contain integers") from exc
        if media_id in seen:
            raise DuplicateMediaSelection("media order contains duplicates")
        seen.add(media_id)
        ordered.append(media_id)
    return ordered


def parse_album_ids(raw: Iterable[object]) -> list[int]:
    """アルバム並べ替えリクエストの ID を整形する（重複は黙って除去）.

    呼び出し側で ``raw`` が空でないリストであることを保証すること。
    """
    ordered: list[int] = []
    seen: set[int] = set()
    for value in raw:
        try:
            album_id = int(value)
        except (TypeError, ValueError) as exc:
            raise InvalidMediaSelection("album ids must be integers") from exc
        if album_id in seen:
            continue
        seen.add(album_id)
        ordered.append(album_id)
    return ordered


def resolve_cover_media_id(
    cover_media_id: int | None,
    media_ids: list[int],
) -> int | None:
    """カバー画像の不変条件を適用する.

    - カバーが収録メディアに含まれない場合は無効化する
    - カバー未設定でメディアがある場合は先頭をカバーにする
    """
    if cover_media_id is not None and cover_media_id not in media_ids:
        cover_media_id = None
    if cover_media_id is None and media_ids:
        cover_media_id = media_ids[0]
    return cover_media_id


__all__ = [
    "AlbumVisibility",
    "parse_media_ids",
    "parse_ordered_media_ids",
    "parse_album_ids",
    "resolve_cover_media_id",
]
