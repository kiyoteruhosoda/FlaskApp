"""Storage domain types and enums."""

from __future__ import annotations

from enum import Enum
from typing import TypeAlias

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


class StorageResolution(Enum):
    """Thumbnail resolution levels."""
    SMALL = "256"
    MEDIUM = "1024" 
    LARGE = "2048"