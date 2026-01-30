"""サムネイル再試行スケジューラのCelery実装."""

from __future__ import annotations

import logging
from typing import Optional

from bounded_contexts.photonest.application.media_processing.interfaces import ThumbnailRetryScheduler
from core.logging_config import setup_task_logging


class RetrySchedulingError(RuntimeError):
    """再試行スケジュールに失敗したことを表す例外."""


class CeleryThumbnailRetryScheduler(ThumbnailRetryScheduler):
    """Celery を利用したサムネイル再試行スケジューラ."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or setup_task_logging(__name__)

    def schedule(
        self,
        *,
        media_id: int,
        force: bool,
        countdown_seconds: int,
    ) -> Optional[str]:
        try:
            from cli.src.celery.tasks import thumbs_generate_task
        except ImportError:
            return None

        try:
            async_result = thumbs_generate_task.apply_async(
                kwargs={"media_id": media_id, "force": force},
                countdown=countdown_seconds,
            )
        except Exception as exc:  # pragma: no cover - Celery 呼び出し失敗時
            self._logger.warning(
                "Failed to schedule thumbnail retry", exc_info=True, extra={"media_id": media_id, "error": str(exc)}
            )
            raise RetrySchedulingError(str(exc)) from exc

        return getattr(async_result, "id", None)
