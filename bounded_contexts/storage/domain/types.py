"""Storage境界文脈のドメイン型定義."""

from __future__ import annotations

from enum import Enum

__all__ = [
    "StorageBackendType",
    "StorageDomain", 
    "StorageIntent",
    "StorageResolution",
]


class StorageBackendType(Enum):
    """Storage backend types."""
    LOCAL = "local"
    S3 = "s3"
    GCS = "gcs"
    AZURE_BLOB = "azure_blob"
    EXTERNAL_REST = "external_rest"
    
    # CDN backends
    AZURE_CDN = "azure_cdn"
    CLOUDFLARE_CDN = "cloudflare_cdn"
    AMAZON_CLOUDFRONT = "amazon_cloudfront"
    GENERIC_CDN = "generic_cdn"


class StorageDomain(Enum):
    """Storage domain categories.

    細分化されたメディア用ドメイン（originals / playback / thumbnails / import）は、
    ``StorageService.for_domain`` で各保存先ディレクトリへ 1:1 に解決される。
    ``MEDIA`` / ``THUMBNAILS`` などの粗いカテゴリは ``StoragePath`` のラベルや
    CDN 連携で用いる。
    """

    # 粗いカテゴリ（StoragePath のラベル等で使用）
    MEDIA = "media"
    THUMBNAILS = "thumbnails"
    TEMP = "temp"
    BACKUPS = "backups"
    DEFAULT = "default"

    # メディア保存先に 1:1 対応する細分化ドメイン（for_domain で解決）
    MEDIA_ORIGINALS = "media_originals"
    MEDIA_PLAYBACK = "media_playback"
    MEDIA_THUMBNAILS = "media_thumbnails"
    MEDIA_IMPORT = "media_import"


class StorageIntent(Enum):
    """Storage intent types."""
    ORIGINAL = "original"
    PLAYBACK = "playback"
    THUMBNAIL = "thumbnail"
    CACHE = "cache"
    READ = "read"  # Added for compatibility
    WRITE = "write"  # Added for compatibility
    DELETE = "delete"  # 削除時のクリーンアップ用
    
    # CDN specific intents
    CDN_OPTIMIZED = "cdn_optimized"
    CDN_CACHED = "cdn_cached"


class StorageResolution(Enum):
    """Thumbnail resolution levels."""
    SMALL = "256"
    MEDIUM = "1024" 
    LARGE = "2048"