"""サムネイル再試行監視ユースケース."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from .interfaces import ThumbnailRetryRepository
from .logger import StructuredMediaTaskLogger
from .thumbnail_service import ThumbnailGenerationService


class ThumbnailRetryMonitorService:
    """期限切れの再試行レコードを処理するアプリケーションサービス."""

    def __init__(
        self,
        *,
        repository: ThumbnailRetryRepository,
        thumbnail_service: ThumbnailGenerationService,
        logger: StructuredMediaTaskLogger,
    ) -> None:
        self._repository = repository
        self._thumbnail_service = thumbnail_service
        self._logger = logger

    def process_due(self, *, limit: int = 50) -> Dict[str, int]:
        now = datetime.now(timezone.utc)
        pending = list(self._repository.iter_due(limit))

        if not pending:
            self._log_idle_state()
            return {
                "processed": 0,
                "rescheduled": 0,
                "cleared": 0,
                "pending_before": 0,
            }

        processed = 0
        rescheduled = 0
        cleared = 0

        for entry in pending:
            processed += 1
            if entry.media_id is None:
                self._repository.mark_canceled(entry, finished_at=now)
                continue

            try:
                media_id = int(entry.media_id)
            except (TypeError, ValueError):
                self._repository.mark_canceled(entry, finished_at=now)
                continue

            self._repository.mark_running(entry, started_at=now)
            result = self._thumbnail_service.generate(
                media_id=media_id,
                operation_id=f"thumbnail-retry-{media_id}",
                request_context={"source": "retry-monitor"},
                force=bool(entry.payload.get("force", False)),
            )
            if result.get("retry_scheduled"):
                rescheduled += 1
            else:
                cleared += 1

        self._logger.info(
            event="thumbnail_generation.retry_monitor",
            message="Processed pending thumbnail retries.",
            operation_id="thumbnail-retry-monitor",
            media_id=0,
            processed=processed,
            rescheduled=rescheduled,
            cleared=cleared,
            pending_before=len(pending),
        )

        return {
            "processed": processed,
            "rescheduled": rescheduled,
            "cleared": cleared,
            "pending_before": len(pending),
        }

    def _log_idle_state(self) -> None:
        disabled = list(self._repository.find_disabled(limit=5))
        alerts = []
        records_to_mark = []
        for entry in disabled:
            payload = entry.payload
            if not payload.get("retry_disabled"):
                continue
            if payload.get("monitor_reported"):
                continue
            alerts.append(
                {
                    "media_id": entry.media_id,
                    "attempts": payload.get("attempts"),
                    "blockers": payload.get("blockers"),
                }
            )
            records_to_mark.append(entry)

        if not alerts:
            return

        self._repository.mark_monitor_reported(records_to_mark)
        self._logger.warning(
            event="thumbnail_generation.retry_monitor_blocked",
            message=(
                "No pending thumbnail retries; some media exhausted their retry budget and require manual attention."
            ),
            operation_id="thumbnail-retry-monitor",
            media_id=0,
            disabled=len(alerts),
            samples=alerts,
        )
