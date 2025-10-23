"""ストレージ関連のドメイン値オブジェクト定義."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StorageDomain(Enum):
    """アプリケーションで利用されるストレージ領域の種別."""

    MEDIA_ORIGINALS = "media.originals"
    MEDIA_PLAYBACK = "media.playback"
    MEDIA_THUMBNAILS = "media.thumbnails"
    MEDIA_IMPORT = "media.import"
    WIKI = "wiki"
    DOCUMENT = "document"


class StorageIntent(Enum):
    """ストレージ操作の目的を表す値オブジェクト."""

    READ = "read"
    WRITE = "write"
    LIST = "list"
    DELETE = "delete"


@dataclass(frozen=True)
class StorageResolution:
    """ストレージ上のパス解決結果."""

    base_path: str | None
    absolute_path: str | None
    exists: bool

