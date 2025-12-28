from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from core.db import db
from core.logging_config import setup_task_logging
from core.models.job_sync import JobSync
from core.models.log import Log
from core.models.picker_session import PickerSession
from core.models.worker_log import WorkerLog

logger = setup_task_logging(__name__)


def cleanup_old_logs(*, retention_days: int = 365) -> dict[str, object]:
    """Physically delete log records older than the retention window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted_counts: dict[str, int] = {"log": 0, "worker_log": 0, "picker_session": 0}

    try:
        log_stmt = delete(Log).where(Log.created_at < cutoff)
        log_result = db.session.execute(log_stmt)
        deleted_counts["log"] = int(log_result.rowcount or 0)

        worker_stmt = delete(WorkerLog).where(WorkerLog.created_at < cutoff)
        worker_result = db.session.execute(worker_stmt)
        deleted_counts["worker_log"] = int(worker_result.rowcount or 0)

        job_sync_exists = (
            select(JobSync.id)
            .where(JobSync.session_id == PickerSession.id)
            .limit(1)
            .exists()
        )
        picker_stmt = (
            delete(PickerSession)
            .where(PickerSession.created_at < cutoff)
            .where(~job_sync_exists)
        )
        picker_result = db.session.execute(picker_stmt)
        deleted_counts["picker_session"] = int(picker_result.rowcount or 0)

        db.session.commit()

        logger.info(
            "Old log cleanup completed",
            extra={
                "event": "logs.cleanup",
                "cutoff": cutoff.isoformat(),
                "deleted_counts": deleted_counts,
                "retention_days": retention_days,
            },
        )

        return {
            "ok": True,
            "deleted": deleted_counts,
            "cutoff": cutoff.isoformat(),
            "retention_days": retention_days,
        }
    except Exception as exc:  # pragma: no cover - defensive logging path
        db.session.rollback()
        logger.error(
            "Old log cleanup failed",
            extra={
                "event": "logs.cleanup.error",
                "cutoff": cutoff.isoformat(),
                "retention_days": retention_days,
            },
            exc_info=True,
        )
        return {"ok": False, "error": str(exc), "retention_days": retention_days}
