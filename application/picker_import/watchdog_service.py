from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Callable, Dict

from core.db import db
from core.models.celery_task import CeleryTaskStatus
from core.models.job_sync import JobSync
from core.models.picker_session import PickerSession
from infrastructure.picker_import.repositories import (
    PickerSelectionRepository,
    PickerSessionRepository,
)


@dataclass
class PickerImportWatchdog:
    """PickerSelectionの状態監視を行うアプリケーションサービス。"""

    selection_repository: PickerSelectionRepository
    session_repository: PickerSessionRepository
    enqueue_func: Callable[[int, int], None]
    logger: logging.Logger

    def run(
        self,
        *,
        lock_lease: int = 120,
        stale_running: int = 600,
        max_attempts: int = 3,
    ) -> Dict[str, int]:
        now = datetime.now(timezone.utc)
        metrics = {"requeued": 0, "failed": 0, "recovered": 0, "republished": 0}

        running = self.selection_repository.list_running()
        for sel in running:
            hb = sel.lock_heartbeat_at
            if hb and hb.tzinfo is None:
                hb = hb.replace(tzinfo=timezone.utc)
            started = sel.started_at
            if started and started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)

            stale = False
            if hb is None or hb < now - timedelta(seconds=lock_lease):
                stale = True
            if started and started < now - timedelta(seconds=stale_running):
                stale = True

            if not stale:
                continue

            if sel.attempts < max_attempts:
                sel.status = "enqueued"
                sel.locked_by = None
                sel.lock_heartbeat_at = None
                sel.started_at = None
                sel.enqueued_at = now
                sel.last_transition_at = now
                metrics["requeued"] += 1
                self._emit(
                    "info",
                    "scavenger.requeue",
                    selection_id=sel.id,
                    attempts=sel.attempts,
                    ts=now.isoformat(),
                )
            else:
                sel.status = "failed"
                sel.locked_by = None
                sel.lock_heartbeat_at = None
                sel.finished_at = now
                sel.last_transition_at = now
                metrics["failed"] += 1
                self._emit(
                    "info",
                    "scavenger.finalize_failed",
                    selection_id=sel.id,
                    attempts=sel.attempts,
                    ts=now.isoformat(),
                )

        if metrics["requeued"] or metrics["failed"]:
            self.selection_repository.commit()

        failed_rows = self.selection_repository.list_failed()
        for sel in failed_rows:
            lt = sel.last_transition_at
            if lt and lt.tzinfo is None:
                lt = lt.replace(tzinfo=timezone.utc)
            if lt and lt + timedelta(seconds=60 * (2 ** sel.attempts)) <= now:
                sel.status = "enqueued"
                sel.enqueued_at = now
                sel.finished_at = None
                sel.last_transition_at = now
                metrics["recovered"] += 1
                self._emit(
                    "info",
                    "scavenger.requeue",
                    selection_id=sel.id,
                    attempts=sel.attempts,
                    ts=now.isoformat(),
                )

        if metrics["recovered"]:
            self.selection_repository.commit()

        enqueued_rows = self.selection_repository.list_enqueued()
        stale_threshold = now - timedelta(minutes=5)
        for sel in enqueued_rows:
            enq_at = sel.enqueued_at or sel.last_transition_at
            if not enq_at:
                continue
            if enq_at.tzinfo is None:
                enq_at = enq_at.replace(tzinfo=timezone.utc)
            if enq_at < stale_threshold:
                self.enqueue_func(sel.id, sel.session_id)
                sel.enqueued_at = now
                metrics["republished"] += 1
                self._emit(
                    "warning",
                    "watchdog.republish",
                    selection_id=sel.id,
                    ts=now.isoformat(),
                )

        if metrics["republished"]:
            self.selection_repository.commit()

        importing_sessions: list[PickerSession] = self.session_repository.list_importing()
        metrics["completed_sessions"] = 0

        for ps in importing_sessions:
            selections = self.selection_repository.list_by_session(ps.id)
            if not selections:
                ps.status = "imported"
                ps.last_progress_at = now
                ps.updated_at = now
                self._finalize_job(ps, now, {})
                metrics["completed_sessions"] += 1
                self._emit(
                    "info",
                    "picker.session.auto_complete",
                    session_id=ps.id,
                    status="imported",
                    reason="no_selections",
                    ts=now.isoformat(),
                )
                continue

            terminal_states = {"imported", "dup", "failed", "expired"}
            all_terminal = all(sel.status in terminal_states for sel in selections)
            if not all_terminal:
                continue

            status_counts: Dict[str, int] = {}
            for sel in selections:
                status_counts[sel.status] = status_counts.get(sel.status, 0) + 1

            has_imported = status_counts.get("imported", 0) > 0 or status_counts.get("dup", 0) > 0
            has_failed = status_counts.get("failed", 0) > 0 or status_counts.get("expired", 0) > 0

            if has_imported and not has_failed:
                ps.status = "imported"
            elif has_imported and has_failed:
                ps.status = "imported"
            else:
                ps.status = "error"

            ps.last_progress_at = now
            ps.updated_at = now
            self._finalize_job(ps, now, status_counts)
            metrics["completed_sessions"] += 1
            self._emit(
                "info",
                "watchdog.session.complete",
                session_id=ps.id,
                status=ps.status,
                counts=status_counts,
                ts=now.isoformat(),
            )

        if metrics["completed_sessions"]:
            db.session.commit()

        return metrics

    def _finalize_job(self, ps: PickerSession, now: datetime, status_counts: Dict[str, int]) -> None:
        job = (
            JobSync.query.filter_by(target="picker_import", session_id=ps.id)
            .order_by(JobSync.id.desc())
            .first()
        )
        if not job or job.status not in ("queued", "running"):
            return

        job.finished_at = now
        if ps.status == "imported":
            job.status = "success"
        else:
            job.status = "failed"

        stats = job.stats_json or "{}"
        try:
            payload = json.loads(stats)
        except Exception:
            payload = {}
        payload["countsByStatus"] = status_counts
        payload["completed_at"] = now.isoformat()
        job.stats_json = json.dumps(payload)

        if job.celery_task:
            job.celery_task.finished_at = now
            if ps.status == "imported":
                job.celery_task.status = CeleryTaskStatus.SUCCESS
                job.celery_task.error_message = None
                job.celery_task.set_result({"countsByStatus": status_counts, "status": "success"})
            else:
                job.celery_task.status = CeleryTaskStatus.FAILED
                job.celery_task.error_message = None
                job.celery_task.set_result({"countsByStatus": status_counts, "status": job.status})

        db.session.add(job)

    def _emit(self, level: str, event: str, **payload: object) -> None:
        log = getattr(self.logger, level, self.logger.info)
        message = json.dumps(payload, default=str)
        log(message, extra={"event": event})
