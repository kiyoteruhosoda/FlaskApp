"""証明書機能のSQLAlchemyモデル"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB

from core.db import db


class CertificateGroupEntity(db.Model):
    """証明書グループのマスタテーブル"""

    __tablename__ = "certificate_groups"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    group_code = db.Column(db.String(64), nullable=False, unique=True)
    display_name = db.Column(db.String(128), nullable=True)
    auto_rotate = db.Column(db.Boolean, nullable=False, default=True)
    rotation_threshold_days = db.Column(db.Integer, nullable=False)
    key_type = db.Column(db.String(16), nullable=False)
    key_curve = db.Column(db.String(32), nullable=True)
    key_size = db.Column(db.Integer, nullable=True)
    subject = db.Column(db.JSON().with_variant(JSONB, "postgresql"), nullable=False)
    usage_type = db.Column(db.String(32), nullable=False, index=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    certificates = db.relationship(
        "IssuedCertificateEntity",
        back_populates="group",
        lazy="selectin",
    )


class IssuedCertificateEntity(db.Model):
    """発行済み証明書を保持するテーブル"""

    __tablename__ = "issued_certificates"

    kid = db.Column(db.String(64), primary_key=True)
    usage_type = db.Column(db.String(32), nullable=False, index=True)
    group_id = db.Column(db.BigInteger, db.ForeignKey("certificate_groups.id", ondelete="SET NULL"))
    certificate_pem = db.Column(db.Text, nullable=False)
    jwk = db.Column(db.JSON().with_variant(JSONB, "postgresql"), nullable=False)
    issued_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=True, index=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revocation_reason = db.Column(db.Text, nullable=True)
    auto_rotated_from_kid = db.Column(db.String(64), nullable=True)

    group = db.relationship(
        CertificateGroupEntity,
        back_populates="certificates",
        lazy="joined",
    )


class CertificateEventEntity(db.Model):
    """証明書操作の監査ログを保持するテーブル"""

    __tablename__ = "certificate_events"

    id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    actor = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(64), nullable=False)
    target_kid = db.Column(db.String(64), nullable=True, index=True)
    target_group_code = db.Column(db.String(64), nullable=True, index=True)
    reason = db.Column(db.Text, nullable=True)
    details = db.Column(db.JSON().with_variant(JSONB, "postgresql"), nullable=True)
    occurred_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
