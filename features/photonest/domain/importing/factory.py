"""メディアエンティティの生成を担当するファクトリ."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Protocol, runtime_checkable

from features.photonest.domain.local_import.entities import ImportFile

from ..local_import.media_file import MediaFileAnalysis, MediaFileAnalyzer
from .media import Media


@runtime_checkable
class GoogleMediaLike(Protocol):
    id: str
    filename: str
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None
    duration_ms: int | None
    shot_at: datetime | None
    download_url: str | None
    checksum: str | None
    is_video: bool | None
    orientation: int | None
    perceptual_hash: str | None
    exif: Dict[str, Any]
    video_metadata: Dict[str, Any]


@dataclass(slots=True)
class MediaFactory:
    """生ファイルからドメインエンティティを生成する."""

    analyzer: MediaFileAnalyzer = field(default_factory=MediaFileAnalyzer)

    def create_from_path(self, file_path: str, *, origin: str, extras: Dict[str, Any] | None = None) -> Media:
        analysis = self.analyzer.analyze(file_path)
        return Media(analysis=analysis, origin=origin, extras=extras or {})

    def create_from_google_media(
        self,
        item: GoogleMediaLike,
        *,
        origin: str = "google",
        extras: Dict[str, Any] | None = None,
    ) -> Media:
        """Google フォト API メタデータから :class:`Media` を生成する."""

        pseudo_path = item.download_url or f"google://{item.id}/{item.filename}"
        source = ImportFile(pseudo_path)

        extension = Path(item.filename).suffix.lower() if item.filename else source.extension
        is_video = (
            item.is_video
            if item.is_video is not None
            else (item.mime_type.lower().startswith("video/") if item.mime_type else False)
        )

        shot_at = item.shot_at or datetime.now(timezone.utc)

        analysis = MediaFileAnalysis(
            source=source,
            extension=extension,
            file_size=item.size_bytes,
            file_hash=item.checksum or item.id,
            mime_type=item.mime_type,
            is_video=is_video,
            width=item.width,
            height=item.height,
            duration_ms=item.duration_ms,
            orientation=item.orientation,
            shot_at=shot_at,
            exif_data=dict(item.exif or {}),
            video_metadata=dict(item.video_metadata or {}),
            destination_filename=item.filename,
            relative_path=item.id,
            perceptual_hash=item.perceptual_hash,
        )

        payload = {"google_media_id": item.id}
        if extras:
            payload.update(extras)

        return Media(analysis=analysis, origin=origin, extras=payload)


__all__ = ["MediaFactory"]
