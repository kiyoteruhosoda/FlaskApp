from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import db


class CertificatePrivateKeyEntity(db.Model):
    """発行済み証明書に紐づく秘密鍵を保持するテーブル"""

    __tablename__ = "certificate_private_keys"

    kid: Mapped[str] = mapped_column(
        db.String(64),
        db.ForeignKey("issued_certificates.kid", ondelete="CASCADE"),
        primary_key=True,
    )
    group_id: Mapped[int | None] = mapped_column(
        db.BigInteger,
        db.ForeignKey("certificate_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    private_key_pem: Mapped[str] = mapped_column(db.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(db.DateTime, nullable=True, index=True)

    certificate: Mapped["IssuedCertificateEntity"] = relationship(
        "IssuedCertificateEntity",
        back_populates="private_key",
        lazy="joined",
    )
    group: Mapped["CertificateGroupEntity | None"] = relationship(
        "CertificateGroupEntity",
        back_populates="private_keys",
        lazy="joined",
    )
