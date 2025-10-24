from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import db

if TYPE_CHECKING:  # pragma: no cover
    from core.models.celery_task import CeleryTaskRecord

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class JobSync(db.Model):
    """Synchronization job record for Celery executions."""

    __tablename__ = "job_sync"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(db.String(50), nullable=False)
    task_name: Mapped[str] = mapped_column(
        db.String(255),
        nullable=False,
        default="",
        server_default="",
    )
    queue_name: Mapped[str | None] = mapped_column(db.String(120), nullable=True)
    trigger: Mapped[str] = mapped_column(
        db.String(32),
        nullable=False,
        default="worker",
        server_default="worker",
    )
    account_id: Mapped[int | None] = mapped_column(BigInt, nullable=True)
    session_id: Mapped[int | None] = mapped_column(
        BigInt,
        db.ForeignKey("picker_session.id"),
        nullable=True,
    )
    celery_task_id: Mapped[int | None] = mapped_column(
        BigInt,
        db.ForeignKey("celery_task.id"),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
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
    args_json: Mapped[str] = mapped_column(
        db.Text,
        nullable=False,
        default="{}",
        server_default="{}",
    )
    stats_json: Mapped[str] = mapped_column(
        db.Text,
        nullable=False,
        default="{}",
        server_default="{}",
    )

    celery_task: Mapped["CeleryTaskRecord | None"] = relationship(
        "CeleryTaskRecord",
        back_populates="job_syncs",
        lazy="joined",
    )


__all__ = ["JobSync"]
