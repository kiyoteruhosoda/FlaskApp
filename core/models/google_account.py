from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import db
from core.crypto import decrypt

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class GoogleAccount(db.Model):
    __tablename__ = "google_account"
    __table_args__ = (
        db.UniqueConstraint("user_id", "email", name="uq_user_google_email"),
    )

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    # ユーザー未紐付けのアカウントを許容するため user_id を nullable に
    user_id: Mapped[int | None] = mapped_column(
        BigInt,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(db.String(255), nullable=False)
    status: Mapped[str] = mapped_column(db.String(20), nullable=False, default="active")
    scopes: Mapped[str] = mapped_column(db.Text, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    oauth_token_json: Mapped[str | None] = mapped_column(db.Text, nullable=True)
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

    # リレーションシップ
    user: Mapped["User | None"] = relationship(
        "User",
        back_populates="google_accounts",
    )
    picker_sessions: Mapped[list["PickerSession"]] = relationship(
        "PickerSession",
        back_populates="account",
    )
    media_items: Mapped[list["Media"]] = relationship(
        "Media",
        back_populates="account",
    )

    def scopes_list(self) -> list[str]:
        """Return scopes as list."""
        if not self.scopes:
            return []
        return [s.strip() for s in self.scopes.split(",") if s.strip()]

    def refresh_token_expires_at(self, *, as_datetime: bool = False) -> Any:
        """Return refresh token expiry timestamp."""
        if not self.oauth_token_json:
            return None
        try:
            data = json.loads(decrypt(self.oauth_token_json))
        except Exception:
            return None

        expiry = data.get("refresh_token_expires_at") or data.get("refresh_token_expiry")
        if expiry:
            return self._coerce_expiry(expiry, as_datetime)

        expires_in = data.get("refresh_token_expires_in")
        if expires_in:
            try:
                base = self.last_synced_at or datetime.now(timezone.utc)
                dt = base + timedelta(seconds=int(expires_in))
                return dt if as_datetime else dt.isoformat()
            except Exception:
                return None
        return None

    @staticmethod
    def _coerce_expiry(value, as_datetime):
        if not as_datetime:
            return value
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, str):
            normalized = value.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(normalized)
            except ValueError:
                return None
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        return None
