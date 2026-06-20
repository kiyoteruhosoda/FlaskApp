"""Album 集約のドメインモデル.

フレームワーク・DB・IO に依存しない純粋なビジネスルールのみを置く。
"""
from __future__ import annotations

from .errors import (
    AlbumDomainError,
    DuplicateMediaSelection,
    InvalidAlbumVisibility,
    InvalidMediaSelection,
)
from .value_objects import (
    AlbumVisibility,
    parse_album_ids,
    parse_media_ids,
    parse_ordered_media_ids,
    resolve_cover_media_id,
)

__all__ = [
    "AlbumVisibility",
    "AlbumDomainError",
    "InvalidAlbumVisibility",
    "InvalidMediaSelection",
    "DuplicateMediaSelection",
    "parse_media_ids",
    "parse_ordered_media_ids",
    "parse_album_ids",
    "resolve_cover_media_id",
]
