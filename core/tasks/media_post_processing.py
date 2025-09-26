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
from .thumbs_generate import thumbs_generate
from .transcode import transcode_worker


_logger = setup_task_logging(__name__)


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
) -> Dict[str, Any]:
    """Synchronously generate thumbnails for *media_id* with structured logging.

    Returns the raw result dictionary from :func:`thumbs_generate` (or a
    synthesized error response when the worker raises an exception).
    """

    logger = logger_override or _logger
    op_id = operation_id or str(uuid4())

    try:
        result = thumbs_generate(media_id=media_id)
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
            _structured_task_log(
                logger,
                level="info",
                event="video_transcoding.skipped",
                message=f"Video playback already {pb.status}.",
                operation_id=op_id,
                media_id=media_id,
                request_context=request_context,
                playback_status=pb.status,
            )
            return {
                "ok": pb.status == "done",
                "note": f"already_{pb.status}",
                "playback_status": pb.status,
            }

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

