"""ドメインエンティティの生成・更新ロジック."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from core.models.photo_models import Exif, Media, MediaItem, PhotoMetadata, VideoMetadata

from .media_file import MediaFileAnalysis


@dataclass(frozen=True)
class MediaItemAggregate:
    """MediaItem と関連メタデータの集約."""

    media_item: MediaItem
    photo_metadata: Optional[PhotoMetadata]
    video_metadata: Optional[VideoMetadata]


def build_media_item_from_analysis(analysis: MediaFileAnalysis) -> MediaItemAggregate:
    """解析結果から MediaItem を生成する。"""

    item_type = "VIDEO" if analysis.is_video else "PHOTO"
    media_item = MediaItem(
        id=f"local_{uuid.uuid4().hex[:16]}",
        type=item_type,
        mime_type=analysis.mime_type,
        filename=analysis.source.name,
        width=analysis.width,
        height=analysis.height,
        camera_make=analysis.exif_data.get("Make"),
        camera_model=analysis.exif_data.get("Model"),
    )

    if analysis.is_video:
        video_metadata = VideoMetadata(
            fps=analysis.video_metadata.get("fps"),
            processing_status=_resolve_processing_status(
                analysis.video_metadata.get("processing_status")
            ),
        )
        media_item.video_metadata = video_metadata
        return MediaItemAggregate(media_item, None, video_metadata)

    photo_metadata = None
    if analysis.exif_data:
        photo_metadata = PhotoMetadata(
            focal_length=analysis.exif_data.get("FocalLength"),
            aperture_f_number=analysis.exif_data.get("FNumber"),
            iso_equivalent=analysis.exif_data.get("ISOSpeedRatings"),
            exposure_time=_normalize_exposure_time(analysis.exif_data.get("ExposureTime")),
        )
        media_item.photo_metadata = photo_metadata

    return MediaItemAggregate(media_item, photo_metadata, None)


def update_media_item_from_analysis(media_item: MediaItem, analysis: MediaFileAnalysis):
    """解析結果を既存の MediaItem に適用する。"""

    media_item.mime_type = analysis.mime_type
    media_item.filename = analysis.source.name
    media_item.width = analysis.width
    media_item.height = analysis.height
    media_item.type = "VIDEO" if analysis.is_video else "PHOTO"
    if analysis.exif_data:
        media_item.camera_make = analysis.exif_data.get("Make") or media_item.camera_make
        media_item.camera_model = analysis.exif_data.get("Model") or media_item.camera_model

    if analysis.is_video:
        video_metadata = media_item.video_metadata or VideoMetadata(
            processing_status="UNSPECIFIED"
        )
        video_metadata.fps = analysis.video_metadata.get("fps")
        video_metadata.processing_status = _resolve_processing_status(
            analysis.video_metadata.get("processing_status")
        )
        media_item.video_metadata = video_metadata
        return video_metadata

    if not analysis.exif_data:
        return None

    photo_metadata = media_item.photo_metadata or PhotoMetadata()
    photo_metadata.focal_length = analysis.exif_data.get("FocalLength")
    photo_metadata.aperture_f_number = analysis.exif_data.get("FNumber")
    photo_metadata.iso_equivalent = analysis.exif_data.get("ISOSpeedRatings")
    photo_metadata.exposure_time = _normalize_exposure_time(
        analysis.exif_data.get("ExposureTime")
    )
    media_item.photo_metadata = photo_metadata
    return photo_metadata


def build_media_from_analysis(
    analysis: MediaFileAnalysis,
    *,
    google_media_id: str,
    relative_path: str,
) -> Media:
    """解析結果から Media エンティティを生成する。"""

    media = Media(
        google_media_id=google_media_id,
        account_id=None,
        local_rel_path=relative_path,
        filename=analysis.source.name,
        hash_sha256=analysis.file_hash,
        bytes=analysis.file_size,
        mime_type=analysis.mime_type,
        width=analysis.width,
        height=analysis.height,
        duration_ms=analysis.duration_ms,
        shot_at=analysis.shot_at,
        imported_at=datetime.now(timezone.utc),
        orientation=analysis.orientation,
        is_video=analysis.is_video,
        live_group_id=None,
        is_deleted=False,
        has_playback=False,
    )

    if analysis.exif_data:
        media.camera_make = analysis.exif_data.get("Make") or media.camera_make
        media.camera_model = analysis.exif_data.get("Model") or media.camera_model

    return media


def apply_analysis_to_media_entity(media: Media, analysis: MediaFileAnalysis) -> None:
    """既存 Media に解析結果を適用する。"""

    media.mime_type = analysis.mime_type
    media.hash_sha256 = analysis.file_hash
    media.bytes = analysis.file_size
    if analysis.width is not None:
        media.width = analysis.width
    if analysis.height is not None:
        media.height = analysis.height
    media.duration_ms = analysis.duration_ms
    media.orientation = analysis.orientation
    media.shot_at = analysis.shot_at
    media.is_video = analysis.is_video

    if analysis.exif_data:
        media.camera_make = analysis.exif_data.get("Make") or media.camera_make
        media.camera_model = analysis.exif_data.get("Model") or media.camera_model


def ensure_exif_for_media(media: Media, analysis: MediaFileAnalysis) -> Optional[Exif]:
    """解析結果から EXIF 情報を更新・生成する。"""

    if not analysis.exif_data:
        return None

    exif = media.exif
    if exif is None:
        exif = Exif.query.get(media.id)  # type: ignore[arg-type]
    exif = exif or Exif(media_id=media.id)
    exif.camera_make = analysis.exif_data.get("Make")
    exif.camera_model = analysis.exif_data.get("Model")
    exif.lens = analysis.exif_data.get("LensModel")
    exif.iso = analysis.exif_data.get("ISOSpeedRatings")
    exif.shutter = _normalize_exposure_time(analysis.exif_data.get("ExposureTime"))
    exif.f_number = analysis.exif_data.get("FNumber")
    exif.focal_len = analysis.exif_data.get("FocalLength")
    exif.gps_lat = analysis.exif_data.get("GPSLatitude")
    exif.gps_lng = analysis.exif_data.get("GPSLongitude")
    exif.raw_json = json.dumps(analysis.exif_data, ensure_ascii=False, default=str)
    exif.media_id = media.id
    return exif


def _normalize_exposure_time(value) -> Optional[str]:  # type: ignore[no-untyped-def]
    if value in (None, ""):
        return None
    return str(value)


def _resolve_processing_status(value: Optional[str]) -> str:
    if not value:
        return "UNSPECIFIED"
    return value


__all__ = [
    "MediaItemAggregate",
    "apply_analysis_to_media_entity",
    "build_media_from_analysis",
    "build_media_item_from_analysis",
    "ensure_exif_for_media",
    "update_media_item_from_analysis",
]

