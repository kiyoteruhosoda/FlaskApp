"""動画再生資産生成ユースケース."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from core.db import db
from core.models.photo_models import MediaPlayback

from .logger import StructuredMediaTaskLogger


class MediaPlaybackService:
    """動画の再生用エンコーディング処理を調停する."""

    def __init__(
        self,
        *,
        worker: Callable[..., Dict[str, Any]],
        thumbnail_generator: Optional[Callable[..., Optional[Dict[str, Any]]]],
        thumbnail_regenerator: Optional[Callable[..., Dict[str, Any]]] = None,
        logger: StructuredMediaTaskLogger,
    ) -> None:
        self._worker = worker
        self._thumbnail_generator = thumbnail_generator
        self._thumbnail_regenerator = thumbnail_regenerator
        self._logger = logger

    def prepare(
        self,
        *,
        media_id: int,
        force_regenerate: bool = False,
        operation_id: Optional[str] = None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        op_id = operation_id or str(uuid4())

        if not shutil.which("ffmpeg"):
            self._logger.warning(
                event="video_transcoding.ffmpeg_missing",
                message="ffmpeg not available, skipping video transcoding.",
                operation_id=op_id,
                media_id=media_id,
                request_context=request_context,
            )
            return {"ok": False, "note": "ffmpeg_missing"}

        try:
            playback = MediaPlayback.query.filter_by(media_id=media_id, preset="std1080p").first()
            if not playback:
                return {"ok": False, "note": "playback_missing"}

            if force_regenerate:
                playback.update_paths(None, None)
                db.session.commit()
                result = self._worker(media_playback_id=playback.id, force=True)
                db.session.refresh(playback)
                if result.get("ok"):
                    self._logger.info(
                        event="video_transcoding.regenerated",
                        message="Video transcoding regenerated.",
                        operation_id=op_id,
                        media_id=media_id,
                        request_context=request_context,
                        playback_rel_path=playback.rel_path,
                        poster_rel_path=playback.poster_rel_path,
                    )
                else:
                    self._logger.warning(
                        event="video_transcoding.regenerate_failed",
                        message=result.get("note", "Video transcoding regeneration failed."),
                        operation_id=op_id,
                        media_id=media_id,
                        request_context=request_context,
                        playback_rel_path=playback.rel_path,
                        poster_rel_path=playback.poster_rel_path,
                    )
                    return result

                if self._thumbnail_generator is not None:
                    thumb_result = self._thumbnail_generator(media_id=media_id, force=True)
                    if thumb_result is not None:
                        result = dict(result)
                        result["thumbnails"] = thumb_result
                return result

            if playback.status in {"done", "processing"}:
                if force_regenerate and playback.status == "done":
                    self._logger.info(
                        event="video_transcoding.force_restart",
                        message="Playback regeneration forced; restarting transcoding.",
                        operation_id=op_id,
                        media_id=media_id,
                        request_context=request_context,
                        previous_status=playback.status,
                    )
                    playback.status = "pending"
                    playback.error_msg = None
                    playback.updated_at = datetime.now(timezone.utc)
                    db.session.commit()
                else:
                    thumb_result: Optional[Dict[str, Any]] = None
                    if playback.status == "done":
                        if self._thumbnail_regenerator is not None:
                            thumb_result = self._thumbnail_regenerator(
                                media_id=media_id,
                                operation_id=op_id,
                                request_context=request_context,
                            )
                        elif self._thumbnail_generator is not None:
                            thumb_result = self._thumbnail_generator(media_id=media_id, force=False)

                    log_details: Dict[str, Any] = {"playback_status": playback.status}
                    if thumb_result is not None:
                        log_details.update(
                            thumbnail_ok=thumb_result.get("ok"),
                            thumbnail_generated=thumb_result.get("generated"),
                            thumbnail_skipped=thumb_result.get("skipped"),
                            thumbnail_notes=thumb_result.get("notes"),
                        )

                    self._logger.info(
                        event="video_transcoding.skipped",
                        message=f"Video playback already {playback.status}.",
                        operation_id=op_id,
                        media_id=media_id,
                        request_context=request_context,
                        **log_details,
                    )

                    response: Dict[str, Any] = {
                        "ok": playback.status == "done",
                        "note": f"already_{playback.status}",
                        "playback_status": playback.status,
                    }
                    if thumb_result is not None:
                        response["thumbnails"] = thumb_result
                    return response

            result = self._worker(media_playback_id=playback.id)
            db.session.refresh(playback)
            log_kwargs = dict(
                operation_id=op_id,
                media_id=media_id,
                request_context=request_context,
                width=result.get("width"),
                height=result.get("height"),
                duration_ms=result.get("duration_ms"),
                note=result.get("note"),
                playback_rel_path=playback.rel_path,
                playback_output_path=result.get("output_path"),
                poster_rel_path=playback.poster_rel_path,
                poster_output_path=result.get("poster_path"),
            )
            if result.get("ok"):
                self._logger.info(
                    event="video_transcoding.complete",
                    message="Video transcoding completed.",
                    **log_kwargs,
                )
            else:
                self._logger.warning(
                    event="video_transcoding.failed",
                    message=result.get("note", "Video transcoding failed."),
                    **log_kwargs,
                )
            return result
        except Exception as exc:  # pragma: no cover - 外部依存の例外経路
            self._logger.error(
                event="video_transcoding.exception",
                message=f"Exception during video transcoding: {exc}",
                operation_id=op_id,
                media_id=media_id,
                request_context=request_context,
                exc_info=True,
            )
            return {"ok": False, "note": "exception", "error": str(exc)}
