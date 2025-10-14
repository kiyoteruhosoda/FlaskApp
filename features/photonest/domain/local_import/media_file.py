"""メディアファイルの解析ロジック."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Protocol

from core.utils import get_file_date_from_exif, get_file_date_from_name

from .entities import ImportFile
from .media_metadata import (
    calculate_file_hash,
    extract_exif_data,
    extract_video_metadata,
    generate_filename,
    get_image_dimensions,
    get_relative_path,
    parse_ffprobe_datetime,
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


class MediaMetadataProvider(Protocol):
    """メディアファイル解析に必要なメタデータ取得の抽象化."""

    def calculate_file_hash(self, file_path: str) -> str:
        ...

    def extract_exif_data(self, file_path: str) -> Dict[str, Any]:
        ...

    def extract_video_metadata(self, file_path: str) -> Dict[str, Any]:
        ...

    def generate_filename(self, shot_at: datetime, extension: str, file_hash: str) -> str:
        ...

    def get_image_dimensions(self, file_path: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
        ...

    def get_relative_path(self, shot_at: datetime, destination_filename: str) -> str:
        ...


@dataclass(frozen=True)
class DefaultMediaMetadataProvider:
    """ドメインのメタデータ関数を利用するデフォルト実装."""

    def calculate_file_hash(self, file_path: str) -> str:
        return calculate_file_hash(file_path)

    def extract_exif_data(self, file_path: str) -> Dict[str, Any]:
        return extract_exif_data(file_path)

    def extract_video_metadata(self, file_path: str) -> Dict[str, Any]:
        return extract_video_metadata(file_path)

    def generate_filename(self, shot_at: datetime, extension: str, file_hash: str) -> str:
        return generate_filename(shot_at, extension, file_hash)

    def get_image_dimensions(self, file_path: str) -> tuple[Optional[int], Optional[int], Optional[int]]:
        return get_image_dimensions(file_path)

    def get_relative_path(self, shot_at: datetime, destination_filename: str) -> str:
        return get_relative_path(shot_at, destination_filename)


@dataclass(frozen=True)
class MediaFileAnalyzer:
    """メディアファイルの解析ロジックを担当するドメインサービス."""

    metadata_provider: MediaMetadataProvider = field(
        default_factory=DefaultMediaMetadataProvider
    )

    def analyze(self, file_path: str) -> MediaFileAnalysis:
        source = ImportFile(file_path)
        extension = source.extension
        file_size = os.path.getsize(file_path)
        file_hash = self.metadata_provider.calculate_file_hash(file_path)
        is_video = extension in SUPPORTED_VIDEO_EXTENSIONS
        mime_type = MIME_TYPE_BY_EXTENSION.get(extension, DEFAULT_MIME_TYPE)

        width: Optional[int] = None
        height: Optional[int] = None
        orientation: Optional[int] = None
        duration_ms: Optional[int] = None
        exif_data: Dict[str, Any] = {}
        video_metadata: Dict[str, Any] = {}

        if is_video:
            video_metadata = self.metadata_provider.extract_video_metadata(file_path)
            width = video_metadata.get("width")
            height = video_metadata.get("height")
            duration_ms = video_metadata.get("duration_ms")
        else:
            width, height, orientation = self.metadata_provider.get_image_dimensions(file_path)
            exif_data = self.metadata_provider.extract_exif_data(file_path)

        shot_at = _resolve_shot_at(source, exif_data, video_metadata)
        destination_filename = self.metadata_provider.generate_filename(
            shot_at, extension, file_hash
        )
        relative_path = self.metadata_provider.get_relative_path(
            shot_at, destination_filename
        )

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


def analyze_media_file(file_path: str) -> MediaFileAnalysis:
    """ファイルを解析して :class:`MediaFileAnalysis` を返す。"""

    analyzer = MediaFileAnalyzer()
    return analyzer.analyze(file_path)


def _resolve_shot_at(
    source: ImportFile,
    exif_data: Dict[str, Any],
    video_metadata: Dict[str, Any],
) -> datetime:
    """撮影日時を解析する。"""

    def _normalize_video_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return parse_ffprobe_datetime(value)
        return None

    shot_at = get_file_date_from_exif(exif_data)

    if not shot_at and video_metadata:
        normalized = _normalize_video_datetime(video_metadata.get("shot_at"))
        if normalized:
            shot_at = normalized
        else:
            for key in ("creation_time", "shot_at_raw"):
                normalized = _normalize_video_datetime(video_metadata.get(key))
                if normalized:
                    shot_at = normalized
                    break

    if not shot_at:
        shot_at = get_file_date_from_name(source.name)
    if not shot_at:
        shot_at = datetime.fromtimestamp(source.path.stat().st_mtime, tz=timezone.utc)
    return shot_at


__all__ = [
    "DefaultMediaMetadataProvider",
    "MediaFileAnalysis",
    "MediaFileAnalyzer",
    "MediaMetadataProvider",
    "analyze_media_file",
]

