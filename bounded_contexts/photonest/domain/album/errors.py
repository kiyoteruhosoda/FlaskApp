"""Album ドメインの業務例外.

技術例外（DB エラー等）はここに置かない。ドメインの不変条件違反のみを表す。
"""
from __future__ import annotations


class AlbumDomainError(Exception):
    """Album 集約に関するドメイン例外の基底クラス."""


class InvalidAlbumVisibility(AlbumDomainError):
    """公開範囲（visibility）として許可されない値が指定された."""


class InvalidMediaSelection(AlbumDomainError):
    """メディア選択（mediaIds 等）の形式が不正である."""


class DuplicateMediaSelection(InvalidMediaSelection):
    """並び順指定の中に同一メディアが重複している."""


__all__ = [
    "AlbumDomainError",
    "InvalidAlbumVisibility",
    "InvalidMediaSelection",
    "DuplicateMediaSelection",
]
