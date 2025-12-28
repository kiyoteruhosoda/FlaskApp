"""pHash 計算アダプタ."""
from __future__ import annotations

from dataclasses import dataclass, replace

from ...domain.importing.media import Media
from ...domain.local_import.media_metadata import calculate_perceptual_hash


@dataclass(slots=True)
class HasherAdapter:
    """ドメインから利用される pHash 計算アダプタ."""

    def normalize(self, media: Media) -> Media:
        analysis = media.analysis
        if analysis.perceptual_hash:
            return media

        phash = calculate_perceptual_hash(
            analysis.source.absolute_path,
            is_video=analysis.is_video,
            duration_ms=analysis.duration_ms,
        )
        updated = replace(analysis, perceptual_hash=phash)
        return Media(analysis=updated, origin=media.origin, extras=dict(media.extras))


__all__ = ["HasherAdapter"]
