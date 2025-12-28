from __future__ import annotations

from datetime import datetime, timezone

from ..db import db
from sqlalchemy.orm import Mapped, mapped_column


class Log(db.Model):
    __tablename__ = "log"

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    level: Mapped[str] = mapped_column(db.String(50), nullable=False)
    event: Mapped[str] = mapped_column(db.String(50), nullable=False)
    message: Mapped[str] = mapped_column(db.Text, nullable=False)
    trace: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    path: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(db.String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


__all__ = ["Log"]
