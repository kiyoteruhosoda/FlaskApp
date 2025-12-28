"""ローカルインポートのポリシー定義."""

from __future__ import annotations

SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tiff",
    ".tif",
    ".bmp",
    ".heic",
    ".heif",
}

SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".m4v",
    ".3gp",
    ".webm",
}

SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS

MIME_TYPE_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/bmp",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".m4v": "video/mp4",
    ".3gp": "video/3gpp",
    ".webm": "video/webm",
}

DEFAULT_MIME_TYPE = "application/octet-stream"


__all__ = [
    "SUPPORTED_IMAGE_EXTENSIONS",
    "SUPPORTED_VIDEO_EXTENSIONS",
    "SUPPORTED_EXTENSIONS",
    "MIME_TYPE_BY_EXTENSION",
    "DEFAULT_MIME_TYPE",
]

