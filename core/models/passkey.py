"""Passkey credential model definition."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import db

if TYPE_CHECKING:  # pragma: no cover
    from core.models.user import User

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class PasskeyCredential(db.Model):
    """Persisted WebAuthn credential bound to a user account."""

    __tablename__ = "passkey_credential"
    __table_args__ = (
        db.UniqueConstraint("credential_id", name="uq_passkey_credential_id"),
    )

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInt,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    credential_id: Mapped[str] = mapped_column(db.String(255), nullable=False)
    public_key: Mapped[str] = mapped_column(db.Text, nullable=False)
    sign_count: Mapped[int] = mapped_column(db.BigInteger, nullable=False, default=0)
    transports: Mapped[list[str] | None] = mapped_column(db.JSON, nullable=True)
    name: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    attestation_format: Mapped[str | None] = mapped_column(db.String(64), nullable=True)
    aaguid: Mapped[str | None] = mapped_column(db.String(64), nullable=True)
    backup_eligible: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=False)
    backup_state: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        db.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="passkey_credentials",
    )

    def touch(self) -> None:
        """Update the ``updated_at`` timestamp to the current UTC time."""

        self.updated_at = datetime.now(timezone.utc)
