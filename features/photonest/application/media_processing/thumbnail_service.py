"""サムネイル生成ユースケース."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from features.photonest.domain.media_processing import RetryBlockers

from .logger import StructuredMediaTaskLogger
from .retry_service import RetryScheduleResult, ThumbnailRetryService


class ThumbnailGenerationService:
    """サムネイル生成と再試行制御を調停する."""

    def __init__(
        self,
        *,
        generator: Callable[..., Dict[str, Any]],
        retry_service: ThumbnailRetryService,
        logger: StructuredMediaTaskLogger,
        playback_not_ready_note: str,
    ) -> None:
        self._generator = generator
        self._retry_service = retry_service
        self._logger = logger
        self._playback_not_ready_note = playback_not_ready_note

    def generate(
        self,
        *,
        media_id: int,
        force: bool = False,
        operation_id: Optional[str] = None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        op_id = operation_id or str(uuid4())
        try:
            result = self._generator(media_id=media_id, force=force)
        except Exception as exc:  # pragma: no cover - 例外経路は外部依存
            self._logger.error(
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

        retry_blockers = RetryBlockers.from_raw(result.get("retry_blockers"))
        retry_details: Optional[Dict[str, Any]] = None
        retry_result: Optional[RetryScheduleResult] = None

        if result.get("ok"):
            self._log_success(
                media_id=media_id,
                op_id=op_id,
                request_context=request_context,
                generated=generated,
                skipped=skipped,
                notes=notes,
                blockers=retry_blockers,
            )
            if notes == self._playback_not_ready_note:
                retry_result = self._retry_service.schedule_if_allowed(
                    media_id=media_id,
                    force=force,
                    operation_id=op_id,
                    request_context=request_context,
                    blockers=retry_blockers.details if retry_blockers else None,
                )
        else:
            self._logger.warning(
                event="thumbnail_generation.failed",
                message=result.get("notes", "Thumbnail generation failed."),
                operation_id=op_id,
                media_id=media_id,
                request_context=request_context,
                notes=result.get("notes"),
            )

        if retry_result is not None:
            retry_details = self._merge_retry_details(
                retry_result=retry_result,
                blockers=retry_blockers,
            )
        elif retry_blockers:
            retry_details = {"blockers": retry_blockers.details}

        if retry_result and retry_result.scheduled:
            merged = dict(result)
            merged["retry_scheduled"] = True
            if retry_details:
                merged["retry_details"] = retry_details
            return merged

        if retry_details:
            merged = dict(result)
            merged["retry_details"] = retry_details
            result = merged

        should_clear = False
        if retry_result is None:
            should_clear = True
        elif not retry_result.scheduled and not retry_result.keep_record:
            should_clear = True

        if should_clear:
            self._retry_service.clear_success(media_id)

        return result

    def _log_success(
        self,
        *,
        media_id: int,
        op_id: str,
        request_context: Optional[Dict[str, Any]],
        generated: Any,
        skipped: Any,
        notes: Any,
        blockers: Optional[RetryBlockers],
    ) -> None:
        if generated:
            event = "thumbnail_generation.complete"
            message = "Thumbnails generated successfully."
        else:
            event = "thumbnail_generation.skipped"
            blocker_reason = blockers.reason if blockers else None
            if notes:
                if blocker_reason:
                    message = f"Thumbnail generation skipped: {notes}. Root cause: {blocker_reason}."
                else:
                    message = f"Thumbnail generation skipped: {notes}."
            else:
                message = "Thumbnail generation skipped with no thumbnails produced."

        self._logger.info(
            event=event,
            message=message,
            operation_id=op_id,
            media_id=media_id,
            request_context=request_context,
            generated=generated,
            skipped=skipped,
            notes=notes,
            blockers=blockers.details if blockers else None,
        )

    def _merge_retry_details(
        self,
        *,
        retry_result: RetryScheduleResult,
        blockers: Optional[RetryBlockers],
    ) -> Dict[str, Any]:
        details: Dict[str, Any] = {
            "scheduled": retry_result.scheduled,
            "attempts": retry_result.attempts,
            "max_attempts": retry_result.max_attempts,
        }
        if retry_result.countdown is not None:
            details["countdown"] = retry_result.countdown
        if retry_result.celery_task_id is not None:
            details["celery_task_id"] = retry_result.celery_task_id
        if retry_result.reason is not None:
            details["reason"] = retry_result.reason
        if retry_result.blockers:
            details["blockers"] = dict(retry_result.blockers)
        elif blockers:
            details["blockers"] = blockers.details
        if retry_result.keep_record:
            details["keep_record"] = True
        return details
