"""TOTP 管理用のモデル定義"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import db

if TYPE_CHECKING:  # pragma: no cover
    from core.models.user import User

# SQLite 互換の BigInt 定義
BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class TOTPCredential(db.Model):
    """TOTP シークレットを管理するためのモデル"""

    __tablename__ = "totp_credential"
    __table_args__ = (
        db.UniqueConstraint("user_id", "account", "issuer", name="uq_totp_user_account_issuer"),
    )

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInt,
        db.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account: Mapped[str] = mapped_column(db.String(255), nullable=False)
    issuer: Mapped[str] = mapped_column(db.String(255), nullable=False)
    secret: Mapped[str] = mapped_column(db.String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    algorithm: Mapped[str] = mapped_column(db.String(16), nullable=False, default="SHA1")
    digits: Mapped[int] = mapped_column(db.SmallInteger, nullable=False, default=6)
    period: Mapped[int] = mapped_column(db.SmallInteger, nullable=False, default=30)
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
        back_populates="totp_credentials",
    )

    def touch(self) -> None:
        """updated_at を現在時刻で更新"""

        self.updated_at = datetime.now(timezone.utc)
