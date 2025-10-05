"""メディアファイルの解析ロジック."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.utils import get_file_date_from_exif, get_file_date_from_name

from .entities import ImportFile
from .media_metadata import (
    calculate_file_hash,
    extract_exif_data,
    extract_video_metadata,
    generate_filename,
    get_image_dimensions,
    get_relative_path,
)
from .policies import (
    DEFAULT_MIME_TYPE,
    MIME_TYPE_BY_EXTENSION,
    SUPPORTED_VIDEO_EXTENSIONS,
)


@dataclass(frozen=True)
class MediaFileAnalysis:
    """メディアファイルの解析結果."""

    source: ImportFile
    extension: str
    file_size: int
    file_hash: str
    mime_type: str
    is_video: bool
    width: Optional[int]
    height: Optional[int]
    duration_ms: Optional[int]
    orientation: Optional[int]
    shot_at: datetime
    exif_data: Dict[str, Any]
    video_metadata: Dict[str, Any]
    destination_filename: str
    relative_path: str


def analyze_media_file(file_path: str) -> MediaFileAnalysis:
    """ファイルを解析して :class:`MediaFileAnalysis` を返す。"""

    source = ImportFile(file_path)
    extension = source.extension
    file_size = os.path.getsize(file_path)
    file_hash = calculate_file_hash(file_path)
    is_video = extension in SUPPORTED_VIDEO_EXTENSIONS
    mime_type = MIME_TYPE_BY_EXTENSION.get(extension, DEFAULT_MIME_TYPE)

    width: Optional[int] = None
    height: Optional[int] = None
    orientation: Optional[int] = None
    duration_ms: Optional[int] = None
    exif_data: Dict[str, Any] = {}
    video_metadata: Dict[str, Any] = {}

    if is_video:
        video_metadata = extract_video_metadata(file_path)
        width = video_metadata.get("width")
        height = video_metadata.get("height")
        duration_ms = video_metadata.get("duration_ms")
    else:
        width, height, orientation = get_image_dimensions(file_path)
        exif_data = extract_exif_data(file_path)

    shot_at = _resolve_shot_at(source, exif_data, video_metadata)
    destination_filename = generate_filename(shot_at, extension, file_hash)
    relative_path = get_relative_path(shot_at, destination_filename)

    return MediaFileAnalysis(
        source=source,
        extension=extension,
        file_size=file_size,
        file_hash=file_hash,
        mime_type=mime_type,
        is_video=is_video,
        width=width,
        height=height,
        duration_ms=duration_ms,
        orientation=orientation,
        shot_at=shot_at,
        exif_data=exif_data,
        video_metadata=video_metadata,
        destination_filename=destination_filename,
        relative_path=relative_path,
    )


def _resolve_shot_at(
    source: ImportFile,
    exif_data: Dict[str, Any],
    video_metadata: Dict[str, Any],
) -> datetime:
    """撮影日時を解析する。"""

    shot_at = get_file_date_from_exif(exif_data)
    if not shot_at:
        metadata_shot_at = video_metadata.get("shot_at") if video_metadata else None
        if isinstance(metadata_shot_at, datetime):
            shot_at = metadata_shot_at
    if not shot_at:
        shot_at = get_file_date_from_name(source.name)
    if not shot_at:
        shot_at = datetime.fromtimestamp(source.path.stat().st_mtime, tz=timezone.utc)
    return shot_at


__all__ = ["MediaFileAnalysis", "analyze_media_file"]

