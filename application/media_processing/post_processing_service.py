"""メディア取り込み後の後処理ユースケース."""

from __future__ import annotations

from typing import Dict, Optional
from uuid import uuid4

from core.models.photo_models import Media

from .logger import StructuredMediaTaskLogger
from .playback_service import MediaPlaybackService
from .thumbnail_service import ThumbnailGenerationService


class MediaPostProcessingService:
    """メディア種別に応じた後処理パイプラインを提供する."""

    def __init__(
        self,
        *,
        thumbnail_service: ThumbnailGenerationService,
        playback_service: MediaPlaybackService,
        logger: StructuredMediaTaskLogger,
    ) -> None:
        self._thumbnail_service = thumbnail_service
        self._playback_service = playback_service
        self._logger = logger

    def process(
        self,
        *,
        media: Media,
        request_context: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        operation_id = str(uuid4())

        self._logger.info(
            event="media_post_process.start",
            message="Starting post-import processing.",
            operation_id=operation_id,
            media_id=media.id,
            request_context=request_context,
            media_type="video" if media.is_video else "photo",
        )

        if media.is_video:
            playback = self._playback_service.prepare(
                media_id=media.id,
                operation_id=operation_id,
                request_context=request_context,
            )
            return {"playback": playback}

        thumbnails = self._thumbnail_service.generate(
            media_id=media.id,
            operation_id=operation_id,
            request_context=request_context,
        )
        return {"thumbnails": thumbnails}
