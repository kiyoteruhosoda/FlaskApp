from datetime import datetime, timezone

from core.db import db

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class JobSync(db.Model):
    """Synchronization job record."""

    __tablename__ = "job_sync"

    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    target = db.Column(db.String(50), nullable=False)
    account_id = db.Column(BigInt, nullable=False)
    session_id = db.Column(
        BigInt, db.ForeignKey("picker_session.id"), nullable=False
    )
    celery_task_id = db.Column(BigInt, db.ForeignKey("celery_task.id"), nullable=True)
    started_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(
        db.Enum(
            "queued",
            "running",
            "success",
            "partial",
            "failed",
            "canceled",
            name="job_sync_status",
        ),
        nullable=False,
        default="queued",
        server_default="queued",
    )
    stats_json = db.Column(db.Text, nullable=False, default="{}", server_default="{}")

    celery_task = db.relationship("CeleryTaskRecord", backref="job_syncs", lazy="joined")


__all__ = ["JobSync"]

