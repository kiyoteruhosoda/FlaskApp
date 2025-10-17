"""System-wide configuration persisted in the database."""
from __future__ import annotations

from datetime import datetime, timezone

from core.db import db


class SystemSetting(db.Model):
    """Simple key-value store for system configuration."""

    __tablename__ = "system_settings"

    key = db.Column(db.String(120), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


__all__ = ["SystemSetting"]
