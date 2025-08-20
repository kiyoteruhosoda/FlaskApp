from datetime import datetime, timezone

from core.db import db

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class PickerDownloadTask(db.Model):
    __tablename__ = "picker_download_task"

    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    task_id = db.Column(db.String(255), unique=True, nullable=False)
    picker_session_id = db.Column(
        BigInt, db.ForeignKey("picker_session.id"), nullable=False, index=True
    )
    status = db.Column(db.String(20), nullable=False, default="pending")
    cursor = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
