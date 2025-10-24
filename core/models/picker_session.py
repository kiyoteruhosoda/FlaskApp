from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import event, select
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import db

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class PickerSession(db.Model):
    __tablename__ = "picker_session"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    account_id: Mapped[int | None] = mapped_column(
        BigInt,
        db.ForeignKey("google_account.id"),
        nullable=True,
    )  # ローカルインポート用にNULL許可
    session_id: Mapped[str | None] = mapped_column(db.String(255), unique=True, nullable=True)
    picker_uri: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    expire_time: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    polling_config_json: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    picking_config_json: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    media_items_set: Mapped[bool | None] = mapped_column(db.Boolean, nullable=True)
    status: Mapped[str] = mapped_column(
        db.Enum(
            "pending",
            "ready",
            "expanding",
            "processing",
            "enqueued",
            "importing",
            "imported",
            "canceled",
            "expired",
            "error",
            "failed",
            name="picker_session_status",
        ),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    selected_count: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    stats_json: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    last_progress_at: Mapped[datetime | None] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    account: Mapped["GoogleAccount | None"] = relationship(
        "GoogleAccount",
        back_populates="picker_sessions",
        lazy="selectin",
    )
    picker_selections: Mapped[list["PickerSelection"]] = relationship(
        "PickerSelection",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    def stats(self) -> dict[str, Any]:
        try:
            return json.loads(self.stats_json) if self.stats_json else {}
        except Exception:
            return {}

    def set_stats(self, data: Any) -> None:
        self.stats_json = json.dumps(data)


@event.listens_for(PickerSession, "before_insert")
def _ensure_unique_session_id(mapper, connection, target):
    if not target.session_id:
        return

    base_session_id = target.session_id.split("#", 1)[0]
    candidate = target.session_id
    counter = 1

    while connection.scalar(
        select(PickerSession.id)
        .where(PickerSession.session_id == candidate)
        .limit(1)
    ) is not None:
        candidate = f"{base_session_id}#{counter}"
        counter += 1

    target.session_id = candidate
