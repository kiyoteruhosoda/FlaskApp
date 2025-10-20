"""System-wide configuration persisted in the database."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, Text

from core.db import db


class SystemSetting(db.Model):
    """Keyed JSON payload describing application configuration."""

    __tablename__ = "system_settings"
    __table_args__ = {"sqlite_autoincrement": True}

    id = db.Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    setting_key = db.Column(String(100), nullable=False, unique=True)
    setting_json = db.Column(JSON, nullable=False)
    description = db.Column(Text, nullable=True)
    updated_at = db.Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


__all__ = ["SystemSetting"]
