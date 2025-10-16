"""SQLAlchemy models for certificate infrastructure."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB

from core.db import db


class IssuedCertificateEntity(db.Model):
    """Persistent storage for issued certificates."""

    __tablename__ = "issued_certificates"

    kid = db.Column(db.String(64), primary_key=True)
    usage_type = db.Column(db.String(32), nullable=False, index=True)
    certificate_pem = db.Column(db.Text, nullable=False)
    jwk = db.Column(db.JSON().with_variant(JSONB, "postgresql"), nullable=False)
    issued_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revocation_reason = db.Column(db.Text, nullable=True)
