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
    """Storage domain categories."""
    MEDIA = "media"
    THUMBNAILS = "thumbnails"
    TEMP = "temp"
    BACKUPS = "backups"


class StorageIntent(Enum):
    """Storage intent types."""
    ORIGINAL = "original"
    PLAYBACK = "playback"
    THUMBNAIL = "thumbnail"
    CACHE = "cache"
    READ = "read"  # Added for compatibility
    WRITE = "write"  # Added for compatibility
    
    # CDN specific intents
    CDN_OPTIMIZED = "cdn_optimized"
    CDN_CACHED = "cdn_cached"


class StorageResolution(Enum):
    """Thumbnail resolution levels."""
    SMALL = "256"
    MEDIUM = "1024" 
    LARGE = "2048"