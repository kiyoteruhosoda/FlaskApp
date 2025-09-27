"""Utilities for post-import media processing steps.

This module centralises common operations that occur after a media item has
been persisted, such as generating thumbnails for photos or scheduling
transcoding for videos.  Both picker imports and local imports can leverage
these helpers so that the behaviour and logging stay consistent.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from core.db import db
from core.logging_config import log_task_error, log_task_info, setup_task_logging
from core.models.photo_models import Media, MediaPlayback

# These imports are intentionally placed after SQLAlchemy models to avoid
# circular import issues.
from .thumbs_generate import PLAYBACK_NOT_READY_NOTES, thumbs_generate
from .transcode import transcode_worker


_logger = setup_task_logging(__name__)

_THUMBNAIL_RETRY_COUNTDOWN = 300


def _schedule_thumbnail_retry(
    *,
    media_id: int,
    force: bool,
    countdown: int,
    logger: logging.Logger,
    operation_id: str,
    request_context: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Schedule a Celery retry for thumbnail generation.

    Returns metadata about the scheduled retry when the job could be enqueued.
    When Celery is not available the function simply returns ``None`` without
    logging to avoid noisy warnings in test environments.
    """

    try:
        from cli.src.celery.tasks import thumbs_generate_task
    except ImportError:
        return None

    try:
        async_result = thumbs_generate_task.apply_async(
            kwargs={"media_id": media_id, "force": force},
            countdown=countdown,
        )
    except Exception as exc:  # pragma: no cover - network failure path
        _structured_task_log(
            logger,
            level="warning",
            event="thumbnail_generation.retry_failed",
            message="Failed to schedule thumbnail retry.",
            operation_id=operation_id,
            media_id=media_id,
            request_context=request_context,
            countdown=countdown,
            error=str(exc),
        )
        return None

    celery_task_id = getattr(async_result, "id", None)
    retry_eta = getattr(async_result, "eta", None)

    _structured_task_log(
        logger,
        level="info",
        event="thumbnail_generation.retry_scheduled",
        message=f"Playback not ready; retry scheduled in {countdown} seconds.",
        operation_id=operation_id,
        media_id=media_id,
        request_context=request_context,
        countdown=countdown,
        celery_task_id=celery_task_id,
        eta=retry_eta,
        force=force,
    )

    return {
        "countdown": countdown,
        "celery_task_id": celery_task_id,
        "eta": retry_eta,
    }


def _structured_task_log(
    logger: logging.Logger,
    *,
    level: str,
    event: str,
    message: str,
    operation_id: str,
    media_id: int,
    request_context: Optional[Dict[str, Any]] = None,
    exc_info: bool = False,
    **details: Any,
) -> None:
    """Emit a structured JSON log entry for background task processing."""

    payload: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "level": level.upper(),
        "message": message,
        "operationId": operation_id,
        "mediaId": media_id,
    }

    if request_context:
        payload["requestContext"] = request_context

    if details:
        payload["details"] = details

    serialized = json.dumps(payload, ensure_ascii=False, default=str)
    extra = {"event": event, "operation_id": operation_id, "media_id": media_id, **details}

    level_lower = level.lower()
    if level_lower == "info":
        log_task_info(logger, serialized, event=event, operation_id=operation_id, media_id=media_id, **details)
    elif level_lower == "warning":
        logger.warning(serialized, extra=extra)
    else:
        # Errors and unexpected levels fall back to the task error helper so the
        # stack trace (if requested) is persisted in the database logs.
        log_task_error(
            logger,
            serialized,
            event=event,
            exc_info=exc_info,
            operation_id=operation_id,
            media_id=media_id,
            **details,
        )


def enqueue_thumbs_generate(
    media_id: int,
    *,
    logger_override: Optional[logging.Logger] = None,
    operation_id: Optional[str] = None,
    request_context: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Synchronously generate thumbnails for *media_id* with structured logging.

    When the underlying worker reports that playback assets are not yet ready,
    the helper schedules a Celery retry (if available) using a 5 minute delay.

    Returns the raw result dictionary from :func:`thumbs_generate` (or a
    synthesized error response when the worker raises an exception).  When a
    retry is scheduled the returned dictionary includes ``retry_scheduled`` set
    to ``True`` along with ``retry_details`` describing the Celery task.
    """

    logger = logger_override or _logger
    op_id = operation_id or str(uuid4())

    try:
        result = thumbs_generate(media_id=media_id, force=force)
    except Exception as exc:  # pragma: no cover - unexpected failure path
        _structured_task_log(
            logger,
            level="error",
            event="thumbnail_generation.exception",
            message=f"Exception during thumbnail generation: {exc}",
            operation_id=op_id,
            media_id=media_id,
            request_context=request_context,
            exc_info=True,
        )
        return {"ok": False, "note": "exception", "error": str(exc)}

    generated = result.get("generated", [])
    skipped = result.get("skipped", [])
    notes = result.get("notes")
    retry_scheduled = False
    retry_details: Optional[Dict[str, Any]] = None

    if result.get("ok"):
        if generated:
            event = "thumbnail_generation.complete"
            message = "Thumbnails generated successfully."
        else:
            event = "thumbnail_generation.skipped"
            # Provide a clear reason in the log message when nothing was generated
            if notes:
                message = f"Thumbnail generation skipped: {notes}."
            else:
                message = "Thumbnail generation skipped with no thumbnails produced."

        _structured_task_log(
            logger,
            level="info",
            event=event,
            message=message,
            operation_id=op_id,
            media_id=media_id,
            request_context=request_context,
            generated=generated,
            skipped=skipped,
            notes=notes,
        )

        if notes == PLAYBACK_NOT_READY_NOTES:
            retry_details = _schedule_thumbnail_retry(
                media_id=media_id,
                force=force,
                countdown=_THUMBNAIL_RETRY_COUNTDOWN,
                logger=logger,
                operation_id=op_id,
                request_context=request_context,
            )
            retry_scheduled = retry_details is not None
    else:
        _structured_task_log(
            logger,
            level="warning",
            event="thumbnail_generation.failed",
            message=result.get("notes", "Thumbnail generation failed."),
            operation_id=op_id,
            media_id=media_id,
            request_context=request_context,
            notes=result.get("notes"),
        )

    if retry_scheduled:
        result = dict(result)
        result["retry_scheduled"] = True
        if retry_details:
            result["retry_details"] = retry_details

    return result


def enqueue_media_playback(
    media_id: int,
    *,
    logger_override: Optional[logging.Logger] = None,
    operation_id: Optional[str] = None,
    request_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Synchronously prepare video playback assets for *media_id*.

    Returns the result dictionary from :func:`transcode_worker` (or a
    synthesized error response when the preparation cannot even be attempted).
    """

    logger = logger_override or _logger
    op_id = operation_id or str(uuid4())

    if not shutil.which("ffmpeg"):
        _structured_task_log(
            logger,
            level="warning",
            event="video_transcoding.ffmpeg_missing",
            message="ffmpeg not available, skipping video transcoding.",
            operation_id=op_id,
            media_id=media_id,
            request_context=request_context,
        )
        return {"ok": False, "note": "ffmpeg_missing"}

    try:
        pb = MediaPlayback.query.filter_by(media_id=media_id, preset="std1080p").first()
        if not pb:
            media = Media.query.get(media_id)
            if not media:
                _structured_task_log(
                    logger,
                    level="error",
                    event="video_transcoding.media_missing",
                    message="Media record not found for playback generation.",
                    operation_id=op_id,
                    media_id=media_id,
                    request_context=request_context,
                    exc_info=False,
                )
                return {"ok": False, "note": "media_missing"}

            rel_path = str(Path(media.local_rel_path).with_suffix(".mp4"))
            pb = MediaPlayback(
                media_id=media_id,
                preset="std1080p",
                rel_path=rel_path,
                status="pending",
            )
            db.session.add(pb)
            db.session.commit()

        if pb.status in {"done", "processing"}:
            thumb_result: Dict[str, Any] | None = None
            if pb.status == "done":
                thumb_result = enqueue_thumbs_generate(
                    media_id,
                    logger_override=logger,
                    operation_id=op_id,
                    request_context=request_context,
                )

            log_details: Dict[str, Any] = {"playback_status": pb.status}
            if thumb_result is not None:
                log_details.update(
                    thumbnail_ok=thumb_result.get("ok"),
                    thumbnail_generated=thumb_result.get("generated"),
                    thumbnail_skipped=thumb_result.get("skipped"),
                    thumbnail_notes=thumb_result.get("notes"),
                )

            _structured_task_log(
                logger,
                level="info",
                event="video_transcoding.skipped",
                message=f"Video playback already {pb.status}.",
                operation_id=op_id,
                media_id=media_id,
                request_context=request_context,
                **log_details,
            )

            result: Dict[str, Any] = {
                "ok": pb.status == "done",
                "note": f"already_{pb.status}",
                "playback_status": pb.status,
            }
            if thumb_result is not None:
                result["thumbnails"] = thumb_result

            return result

        result = transcode_worker(media_playback_id=pb.id)
        db.session.refresh(pb)
        if result.get("ok"):
            _structured_task_log(
                logger,
                level="info",
                event="video_transcoding.complete",
                message="Video transcoding completed.",
                operation_id=op_id,
                media_id=media_id,
                request_context=request_context,
                width=result.get("width"),
                height=result.get("height"),
                duration_ms=result.get("duration_ms"),
                note=result.get("note"),
                playback_rel_path=pb.rel_path,
                playback_output_path=result.get("output_path"),
                poster_rel_path=pb.poster_rel_path,
                poster_output_path=result.get("poster_path"),
            )
        else:
            _structured_task_log(
                logger,
                level="warning",
                event="video_transcoding.failed",
                message=result.get("note", "Video transcoding failed."),
                operation_id=op_id,
                media_id=media_id,
                request_context=request_context,
                width=result.get("width"),
                height=result.get("height"),
                duration_ms=result.get("duration_ms"),
                note=result.get("note"),
                playback_rel_path=pb.rel_path,
                playback_output_path=result.get("output_path"),
                poster_rel_path=pb.poster_rel_path,
                poster_output_path=result.get("poster_path"),
            )

        return result
    except Exception as exc:  # pragma: no cover - unexpected failure path
        _structured_task_log(
            logger,
            level="error",
            event="video_transcoding.exception",
            message=f"Exception during video transcoding: {exc}",
            operation_id=op_id,
            media_id=media_id,
            request_context=request_context,
            exc_info=True,
        )
        return {"ok": False, "note": "exception", "error": str(exc)}


def process_media_post_import(
    media: Media,
    *,
    logger_override: Optional[logging.Logger] = None,
    request_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute the appropriate post-import processing pipeline for *media*.

    Returns a dictionary summarising the outcome of the triggered tasks.
    """

    logger = logger_override or _logger
    op_id = str(uuid4())

    _structured_task_log(
        logger,
        level="info",
        event="media_post_process.start",
        message="Starting post-import processing.",
        operation_id=op_id,
        media_id=media.id,
        request_context=request_context,
        media_type="video" if media.is_video else "photo",
    )

    results: Dict[str, Any] = {}
    if media.is_video:
        results["playback"] = enqueue_media_playback(
            media.id,
            logger_override=logger,
            operation_id=op_id,
            request_context=request_context,
        )
    else:
        results["thumbnails"] = enqueue_thumbs_generate(
            media.id,
            logger_override=logger,
            operation_id=op_id,
            request_context=request_context,
        )

    return results

