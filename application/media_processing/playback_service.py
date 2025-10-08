"""動画再生資産生成ユースケース."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, Optional, Tuple
from uuid import uuid4

from core.db import db
from core.models.photo_models import Media, MediaPlayback
from core.storage_paths import first_existing_storage_path, storage_path_candidates

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
        self._playback_base_cache: Path | None | bool = False

    def _playback_base_dir(self) -> Path | None:
        """Return the base directory for playback assets if resolvable."""

        if self._playback_base_cache is False:
            base = first_existing_storage_path("FPV_NAS_PLAY_DIR")
            if not base:
                candidates = storage_path_candidates("FPV_NAS_PLAY_DIR")
                base = candidates[0] if candidates else None
            self._playback_base_cache = Path(base) if base else None
        return self._playback_base_cache or None

    def _asset_paths(self, playback: MediaPlayback) -> tuple[str | None, str | None]:
        """Resolve absolute playback and poster paths for *playback*."""

        base = self._playback_base_dir()
        if not base:
            return None, None

        output_path = (base / playback.rel_path).as_posix() if playback.rel_path else None
        poster_path = (
            (base / playback.poster_rel_path).as_posix()
            if playback.poster_rel_path
            else None
        )
        return output_path, poster_path

    def _create_playback_record(
        self,
        *,
        media_id: int,
        operation_id: str,
        request_context: Optional[Dict[str, Any]],
    ) -> Tuple[Optional[MediaPlayback], Optional[Dict[str, Any]]]:
        media = Media.query.get(media_id)
        if media is None:
            self._logger.error(
                event="video_transcoding.media_missing",
                message="Media not found while creating playback record.",
                operation_id=operation_id,
                media_id=media_id,
                request_context=request_context,
            )
            return None, {"ok": False, "note": "media_missing"}

        if not media.is_video:
            self._logger.warning(
                event="video_transcoding.media_not_video",
                message="Playback requested for non-video media.",
                operation_id=operation_id,
                media_id=media_id,
                request_context=request_context,
            )
            return None, {"ok": False, "note": "media_not_video"}

        rel_path = self._derive_playback_rel_path(media)
        now = datetime.now(timezone.utc)
        playback = MediaPlayback(
            media_id=media.id,
            preset="std1080p",
            rel_path=rel_path,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        db.session.add(playback)
        db.session.flush()

        self._logger.info(
            event="video_transcoding.playback_created",
            message="Created playback record for media.",
            operation_id=operation_id,
            media_id=media_id,
            request_context=request_context,
            playback_id=playback.id,
            playback_rel_path=rel_path,
        )

        return playback, None

    @staticmethod
    def _derive_playback_rel_path(media: Media) -> str:
        raw_path = (media.local_rel_path or "").replace("\\", "/")
        parts = []
        for part in raw_path.split("/"):
            if not part or part == ".":
                continue
            if part == "..":
                continue
            parts.append(part)

        if parts:
            cleaned = PurePosixPath(*parts)
        else:
            cleaned = PurePosixPath(f"media_{media.id}")

        if cleaned.suffix.lower() != ".mp4":
            cleaned = cleaned.with_suffix(".mp4")

        return cleaned.as_posix()

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
            needs_rel_path_recovery = False
            if not playback:
                playback, error = self._create_playback_record(
                    media_id=media_id,
                    operation_id=op_id,
                    request_context=request_context,
                )
                if error is not None:
                    return error
            else:
                needs_rel_path_recovery = playback.rel_path is None
                if needs_rel_path_recovery and not force_regenerate:
                    self._logger.warning(
                        event="video_transcoding.playback_rel_path_missing",
                        message="Playback rel_path missing; forcing regeneration.",
                        operation_id=op_id,
                        media_id=media_id,
                        request_context=request_context,
                        playback_id=playback.id,
                    )
                else:
                    needs_rel_path_recovery = False

            if force_regenerate or needs_rel_path_recovery:
                now = datetime.now(timezone.utc)
                if hasattr(playback, "update_paths"):
                    playback.update_paths(None, None)
                else:
                    playback.rel_path = None
                    playback.poster_rel_path = None
                    playback.updated_at = now
                # 取り込み時に再生成を強制した場合でもワーカーが "already_done"
                # で打ち切られないよう、状態を pending に戻しておく。
                playback.status = "pending"
                playback.error_msg = None
                playback.updated_at = now
                db.session.commit()
                result = self._worker(
                    media_playback_id=playback.id,
                    force=True,
                )
                db.session.refresh(playback)
                output_path, poster_path = self._asset_paths(playback)
                if output_path and "output_path" not in result:
                    result["output_path"] = output_path
                if poster_path and "poster_path" not in result:
                    result["poster_path"] = poster_path
                if result.get("ok"):
                    self._logger.info(
                        event="video_transcoding.regenerated",
                        message="Video transcoding regenerated.",
                        operation_id=op_id,
                        media_id=media_id,
                        request_context=request_context,
                        playback_rel_path=playback.rel_path,
                        playback_output_path=output_path,
                        poster_rel_path=playback.poster_rel_path,
                        poster_output_path=poster_path,
                    )
                else:
                    self._logger.warning(
                        event="video_transcoding.regenerate_failed",
                        message=result.get("note", "Video transcoding regeneration failed."),
                        operation_id=op_id,
                        media_id=media_id,
                        request_context=request_context,
                        playback_rel_path=playback.rel_path,
                        playback_output_path=output_path,
                        poster_rel_path=playback.poster_rel_path,
                        poster_output_path=poster_path,
                        error=result.get("error"),
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
                    if playback.rel_path:
                        log_details.setdefault("playback_rel_path", playback.rel_path)
                    if playback.poster_rel_path:
                        log_details.setdefault("poster_rel_path", playback.poster_rel_path)
                    if thumb_result is not None:
                        log_details.update(
                            thumbnail_ok=thumb_result.get("ok"),
                            thumbnail_generated=thumb_result.get("generated"),
                            thumbnail_skipped=thumb_result.get("skipped"),
                            thumbnail_notes=thumb_result.get("notes"),
                        )

                    response: Dict[str, Any] = {
                        "ok": playback.status == "done",
                        "note": f"already_{playback.status}",
                        "playback_status": playback.status,
                    }
                    output_path, poster_path = self._asset_paths(playback)
                    if output_path:
                        log_details.setdefault("playback_output_path", output_path)
                        response["output_path"] = output_path
                    if poster_path:
                        log_details.setdefault("poster_output_path", poster_path)
                        response["poster_path"] = poster_path
                    if thumb_result is not None:
                        response["thumbnails"] = thumb_result

                    self._logger.info(
                        event="video_transcoding.skipped",
                        message=f"Video playback already {playback.status}.",
                        operation_id=op_id,
                        media_id=media_id,
                        request_context=request_context,
                        **log_details,
                    )
                    return response

            result = self._worker(media_playback_id=playback.id)
            db.session.refresh(playback)
            output_path, poster_path = self._asset_paths(playback)
            if output_path and "output_path" not in result:
                result["output_path"] = output_path
            if poster_path and "poster_path" not in result:
                result["poster_path"] = poster_path
            log_kwargs = dict(
                operation_id=op_id,
                media_id=media_id,
                request_context=request_context,
                width=result.get("width"),
                height=result.get("height"),
                duration_ms=result.get("duration_ms"),
                note=result.get("note"),
                error=result.get("error"),
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
