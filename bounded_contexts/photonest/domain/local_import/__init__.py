"""Local import domain objects."""

from .entities import ImportFile, ImportOutcome
from .import_result import ImportTaskResult
from .logging import LogEntry, compose_message, existing_media_destination_context, file_log_context, with_session
from .media_entities import (
    apply_analysis_to_media_entity,
    build_media_from_analysis,
    build_media_item_from_analysis,
    ensure_exif_for_media,
    update_media_item_from_analysis,
)
from .media_file import DefaultMediaMetadataProvider, MediaFileAnalyzer
from .media_metadata import calculate_file_hash, extract_exif_data, extract_video_metadata, get_image_dimensions
from .policies import SUPPORTED_EXTENSIONS
from .session import LocalImportSessionService
from .zip_archive import ZipArchiveService

__all__ = [
    "DefaultMediaMetadataProvider",
    "ImportFile",
    "ImportOutcome",
    "ImportTaskResult",
    "LocalImportSessionService",
    "LogEntry",
    "MediaFileAnalyzer",
    "ZipArchiveService",
    "apply_analysis_to_media_entity",
    "build_media_from_analysis",
    "build_media_item_from_analysis",
    "calculate_file_hash",
    "compose_message",
    "ensure_exif_for_media",
    "existing_media_destination_context",
    "extract_exif_data",
    "extract_video_metadata",
    "file_log_context",
    "get_image_dimensions",
    "SUPPORTED_EXTENSIONS",
    "update_media_item_from_analysis",
    "with_session",
]
