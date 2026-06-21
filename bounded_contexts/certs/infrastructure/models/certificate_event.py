from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db import db


class CertificateEventEntity(db.Model):
    """証明書操作の監査ログを保持するテーブル"""

    __tablename__ = "certificate_events"

    id: Mapped[int] = mapped_column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    actor: Mapped[str] = mapped_column(db.String(255), nullable=False)
    action: Mapped[str] = mapped_column(db.String(64), nullable=False)
    target_kid: Mapped[str | None] = mapped_column(db.String(64), nullable=True, index=True)
    target_group_code: Mapped[str | None] = mapped_column(db.String(64), nullable=True, index=True)
    reason: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    details: Mapped[dict | None] = mapped_column(
        db.JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )
