from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import db


class IssuedCertificateEntity(db.Model):
    """発行済み証明書を保持するテーブル"""

    __tablename__ = "issued_certificates"

    kid: Mapped[str] = mapped_column(db.String(64), primary_key=True)
    usage_type: Mapped[str] = mapped_column(db.String(32), nullable=False, index=True)
    group_id: Mapped[int | None] = mapped_column(
        db.BigInteger,
        db.ForeignKey("certificate_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    certificate_pem: Mapped[str] = mapped_column(db.Text, nullable=False)
    jwk: Mapped[dict] = mapped_column(
        db.JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    auto_rotated_from_kid: Mapped[str | None] = mapped_column(db.String(64), nullable=True)

    group: Mapped["CertificateGroupEntity | None"] = relationship(
        "CertificateGroupEntity",
        back_populates="certificates",
        lazy="joined",
    )
    private_key: Mapped["CertificatePrivateKeyEntity | None"] = relationship(
        "CertificatePrivateKeyEntity",
        back_populates="certificate",
        lazy="joined",
        uselist=False,
    )
