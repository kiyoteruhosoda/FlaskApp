from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Mapped, mapped_column

from ..db import db


BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class WorkerLog(db.Model):
    __tablename__ = "worker_log"
    __table_args__ = (
        db.Index("ix_worker_log_file_task_id", "file_task_id"),
        db.Index(
            "ix_worker_log_file_task_id_progress_step",
            "file_task_id",
            "progress_step",
        ),
    )

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    level: Mapped[str] = mapped_column(db.String(20), nullable=False)
    event: Mapped[str] = mapped_column(db.String(50), nullable=False)
    logger_name: Mapped[str | None] = mapped_column(db.String(120), nullable=True)
    task_name: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    task_uuid: Mapped[str | None] = mapped_column(db.String(36), nullable=True)
    file_task_id: Mapped[str | None] = mapped_column(db.String(64), nullable=True)
    progress_step: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    worker_hostname: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    queue_name: Mapped[str | None] = mapped_column(db.String(120), nullable=True)
    status: Mapped[str | None] = mapped_column(db.String(40), nullable=True)
    message: Mapped[str] = mapped_column(db.Text, nullable=False)
    trace: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    meta_json: Mapped[dict | None] = mapped_column(db.JSON, nullable=True)
    extra_json: Mapped[dict | None] = mapped_column(db.JSON, nullable=True)


__all__ = ["WorkerLog"]
