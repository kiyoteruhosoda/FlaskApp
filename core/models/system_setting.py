"""System-wide configuration persisted in the database."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.db import db


class SystemSetting(db.Model):
    """Keyed JSON payload describing application configuration."""

    __tablename__ = "system_settings"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    setting_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    setting_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


__all__ = ["SystemSetting"]
