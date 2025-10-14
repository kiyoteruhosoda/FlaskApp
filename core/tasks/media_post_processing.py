"""メディア後処理タスク群のアプリケーションサービスラッパー."""

from __future__ import annotations

import shutil as _shutil
from typing import Any, Dict, Optional

from features.photonest.application.media_processing import (
    MediaPlaybackService,
    MediaPostProcessingService,
    StructuredMediaTaskLogger,
    ThumbnailGenerationService,
    ThumbnailRetryMonitorService,
    ThumbnailRetryService,
)
from features.photonest.domain.media_processing import ThumbnailRetryPolicy
from features.photonest.infrastructure.media_processing import (
    CeleryThumbnailRetryScheduler,
    SqlAlchemyThumbnailRetryRepository,
)
from core.logging_config import setup_task_logging
from core.models.photo_models import Media

from .thumbs_generate import PLAYBACK_NOT_READY_NOTES, thumbs_generate
from .transcode import transcode_worker

_THUMBNAIL_RETRY_TASK_NAME = "thumbnail.retry"
_THUMBNAIL_RETRY_COUNTDOWN = 300
_THUMBNAIL_RETRY_MAX_ATTEMPTS = 5

_logger = setup_task_logging(__name__)
shutil = _shutil
_retry_policy = ThumbnailRetryPolicy(_THUMBNAIL_RETRY_MAX_ATTEMPTS)
_retry_repository = SqlAlchemyThumbnailRetryRepository()
_retry_scheduler = CeleryThumbnailRetryScheduler(_logger)


def _build_structured_logger(logger_override: Optional[Any]) -> StructuredMediaTaskLogger:
    return StructuredMediaTaskLogger(logger_override or _logger)


def _build_retry_service(logger: StructuredMediaTaskLogger) -> ThumbnailRetryService:
    return ThumbnailRetryService(
        policy=_retry_policy,
        repository=_retry_repository,
        scheduler=_retry_scheduler,
        logger=logger,
        countdown_seconds=_THUMBNAIL_RETRY_COUNTDOWN,
    )


def _build_thumbnail_service(
    *,
    logger: StructuredMediaTaskLogger,
    retry_service: Optional[ThumbnailRetryService] = None,
) -> ThumbnailGenerationService:
    retry = retry_service or _build_retry_service(logger)
    return ThumbnailGenerationService(
        generator=thumbs_generate,
        retry_service=retry,
        logger=logger,
        playback_not_ready_note=PLAYBACK_NOT_READY_NOTES,
    )


def _build_playback_service(
    logger: StructuredMediaTaskLogger,
    thumbnail_service: Optional[ThumbnailGenerationService] = None,
) -> MediaPlaybackService:
    regenerator = None
    if thumbnail_service is not None:
        regenerator = thumbnail_service.generate
    return MediaPlaybackService(
        worker=transcode_worker,
        thumbnail_generator=thumbs_generate,
        thumbnail_regenerator=regenerator,
        logger=logger,
    )


def _build_post_processing_service(
    logger: StructuredMediaTaskLogger,
) -> MediaPostProcessingService:
    retry_service = _build_retry_service(logger)
    thumbnail_service = _build_thumbnail_service(logger=logger, retry_service=retry_service)
    return MediaPostProcessingService(
        thumbnail_service=thumbnail_service,
        playback_invoker=enqueue_media_playback,
        logger=logger,
    )


def _build_retry_monitor_service(logger: StructuredMediaTaskLogger) -> ThumbnailRetryMonitorService:
    thumbnail_service = _build_thumbnail_service(logger=logger)
    return ThumbnailRetryMonitorService(
        repository=_retry_repository,
        thumbnail_service=thumbnail_service,
        logger=logger,
    )


def enqueue_thumbs_generate(
    media_id: int,
    *,
    logger_override: Optional[Any] = None,
    operation_id: Optional[str] = None,
    request_context: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    logger = _build_structured_logger(logger_override)
    retry_service = _build_retry_service(logger)
    thumbnail_service = _build_thumbnail_service(logger=logger, retry_service=retry_service)
    return thumbnail_service.generate(
        media_id=media_id,
        force=force,
        operation_id=operation_id,
        request_context=request_context,
    )


def enqueue_media_playback(
    media_id: int,
    *,
    logger_override: Optional[Any] = None,
    operation_id: Optional[str] = None,
    request_context: Optional[Dict[str, Any]] = None,
    force_regenerate: bool = False,
) -> Dict[str, Any]:
    logger = _build_structured_logger(logger_override)
    retry_service = _build_retry_service(logger)
    thumbnail_service = _build_thumbnail_service(logger=logger, retry_service=retry_service)
    playback_service = _build_playback_service(logger, thumbnail_service)
    return playback_service.prepare(
        media_id=media_id,
        force_regenerate=force_regenerate,
        operation_id=operation_id,
        request_context=request_context,
    )


def process_due_thumbnail_retries(
    *,
    limit: int = 50,
    logger_override: Optional[Any] = None,
) -> Dict[str, int]:
    logger = _build_structured_logger(logger_override)
    monitor = _build_retry_monitor_service(logger)
    return monitor.process_due(limit=limit)


def process_media_post_import(
    media: Media,
    *,
    logger_override: Optional[Any] = None,
    request_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    logger = _build_structured_logger(logger_override)
    service = _build_post_processing_service(logger)
    return service.process(media=media, request_context=request_context)
