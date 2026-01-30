from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import db


class CertificateGroupEntity(db.Model):
    """証明書グループのマスタテーブル"""

    __tablename__ = "certificate_groups"

    id: Mapped[int] = mapped_column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    group_code: Mapped[str] = mapped_column(db.String(64), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(db.String(128), nullable=True)
    auto_rotate: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=True)
    rotation_threshold_days: Mapped[int] = mapped_column(db.Integer, nullable=False)
    key_type: Mapped[str] = mapped_column(db.String(16), nullable=False)
    key_curve: Mapped[str | None] = mapped_column(db.String(32), nullable=True)
    key_size: Mapped[int | None] = mapped_column(db.Integer, nullable=True)
    subject: Mapped[dict] = mapped_column(
        db.JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )
    usage_type: Mapped[str] = mapped_column(db.String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    certificates: Mapped[list["IssuedCertificateEntity"]] = relationship(
        "IssuedCertificateEntity",
        back_populates="group",
        lazy="selectin",
    )
    private_keys: Mapped[list["CertificatePrivateKeyEntity"]] = relationship(
        "CertificatePrivateKeyEntity",
        back_populates="group",
        lazy="selectin",
    )
