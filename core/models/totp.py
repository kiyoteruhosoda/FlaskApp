"""TOTP 管理用のモデル定義"""
from __future__ import annotations

from datetime import datetime, timezone

from core.db import db

# SQLite 互換の BigInt 定義
BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class TOTPCredential(db.Model):
    """TOTP シークレットを管理するためのモデル"""

    __tablename__ = "totp_credential"
    __table_args__ = (
        db.UniqueConstraint("account", "issuer", name="uq_totp_account_issuer"),
    )

    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    account = db.Column(db.String(255), nullable=False)
    issuer = db.Column(db.String(255), nullable=False)
    secret = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    algorithm = db.Column(db.String(16), nullable=False, default="SHA1")
    digits = db.Column(db.SmallInteger, nullable=False, default=6)
    period = db.Column(db.SmallInteger, nullable=False, default=30)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def touch(self) -> None:
        """updated_at を現在時刻で更新"""

        self.updated_at = datetime.now(timezone.utc)
