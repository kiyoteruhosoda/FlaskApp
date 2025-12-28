"""サムネイル再試行を調停するアプリケーションサービス."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from features.photonest.domain.media_processing import ThumbnailRetryPolicy

from .interfaces import ThumbnailRetryRepository, ThumbnailRetryScheduler
from .logger import StructuredMediaTaskLogger


@dataclass(frozen=True)
class RetryScheduleResult:
    """再試行スケジュール結果を表現する値オブジェクト."""

    scheduled: bool
    attempts: int
    max_attempts: int
    countdown: Optional[int] = None
    celery_task_id: Optional[str] = None
    reason: Optional[str] = None
    keep_record: bool = False
    blockers: Optional[Dict[str, Any]] = None


class ThumbnailRetryService:
    """再試行ポリシーとリポジトリを調停する."""

    def __init__(
        self,
        *,
        policy: ThumbnailRetryPolicy,
        repository: ThumbnailRetryRepository,
        scheduler: ThumbnailRetryScheduler,
        logger: StructuredMediaTaskLogger,
        countdown_seconds: int,
    ) -> None:
        self._policy = policy
        self._repository = repository
        self._scheduler = scheduler
        self._logger = logger
        self._countdown_seconds = countdown_seconds

    def schedule_if_allowed(
        self,
        *,
        media_id: int,
        force: bool,
        operation_id: str,
        request_context: Optional[Dict[str, Any]],
        blockers: Optional[Dict[str, Any]] = None,
    ) -> Optional[RetryScheduleResult]:
        entry = self._repository.get_or_create(media_id)
        decision = self._policy.decide(entry.attempts)

        if not decision.can_retry:
            self._repository.mark_exhausted(entry, force=force, blockers=blockers)
            self._logger.warning(
                event="thumbnail_generation.retry_exhausted",
                message="Retry limit reached; no further thumbnail retries will be scheduled.",
                operation_id=operation_id,
                media_id=media_id,
                request_context=request_context,
                attempts=entry.attempts,
                max_attempts=self._policy.max_attempts,
                blockers=blockers,
            )
            return RetryScheduleResult(
                scheduled=False,
                attempts=entry.attempts,
                max_attempts=self._policy.max_attempts,
                reason=decision.reason,
                keep_record=decision.keep_record,
                blockers=blockers,
            )

        try:
            celery_task_id = self._scheduler.schedule(
                media_id=media_id,
                force=force,
                countdown_seconds=self._countdown_seconds,
            )
        except Exception as exc:  # pragma: no cover - スケジューラ例外経路
            self._logger.warning(
                event="thumbnail_generation.retry_failed",
                message="Failed to schedule thumbnail retry.",
                operation_id=operation_id,
                media_id=media_id,
                request_context=request_context,
                countdown=self._countdown_seconds,
                error=str(exc),
            )
            return None
        if celery_task_id is None:
            return None

        self._repository.persist_scheduled(
            entry,
            countdown_seconds=self._countdown_seconds,
            force=force,
            celery_task_id=celery_task_id,
            attempt=decision.attempt_number,
            blockers=blockers,
        )
        self._logger.info(
            event="thumbnail_generation.retry_scheduled",
            message=f"Playback not ready; retry scheduled in {self._countdown_seconds} seconds.",
            operation_id=operation_id,
            media_id=media_id,
            request_context=request_context,
            countdown=self._countdown_seconds,
            celery_task_id=celery_task_id,
            force=force,
            attempts=decision.attempt_number,
            max_attempts=self._policy.max_attempts,
            blockers=blockers,
        )

        return RetryScheduleResult(
            scheduled=True,
            countdown=self._countdown_seconds,
            celery_task_id=celery_task_id,
            attempts=decision.attempt_number,
            max_attempts=self._policy.max_attempts,
            blockers=blockers,
        )

    def clear_success(self, media_id: int) -> None:
        self._repository.clear_success(media_id)
