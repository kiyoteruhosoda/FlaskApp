"""Persistent store for issued certificates."""
from __future__ import annotations

from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from sqlalchemy import delete

from core.db import db
from features.certs.domain.models import IssuedCertificate
from features.certs.domain.usage import UsageType

from .models import IssuedCertificateEntity


class IssuedCertificateStore:
    """Database-backed certificate repository."""

    def add(self, cert: IssuedCertificate) -> None:
        pem = cert.certificate.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        entity = IssuedCertificateEntity(
            kid=cert.kid,
            usage_type=cert.usage_type.value,
            certificate_pem=pem,
            jwk=cert.jwk,
            issued_at=cert.issued_at,
            revoked_at=cert.revoked_at,
            revocation_reason=cert.revocation_reason,
        )
        db.session.merge(entity)
        db.session.commit()

    def list_all(self) -> list[IssuedCertificate]:
        query = IssuedCertificateEntity.query.order_by(IssuedCertificateEntity.issued_at.desc())
        return [self._to_domain(entity) for entity in query.all()]

    def list_by_usage(self, usage: UsageType) -> list[IssuedCertificate]:
        query = (
            IssuedCertificateEntity.query.filter_by(usage_type=usage.value)
            .order_by(IssuedCertificateEntity.issued_at.desc())
        )
        return [self._to_domain(entity) for entity in query.all()]

    def get(self, kid: str) -> IssuedCertificate | None:
        entity = db.session.get(IssuedCertificateEntity, kid)
        if entity is None:
            return None
        return self._to_domain(entity)

    def revoke(self, kid: str, reason: str | None = None) -> IssuedCertificate | None:
        entity = db.session.get(IssuedCertificateEntity, kid)
        if entity is None:
            return None
        entity.revoked_at = datetime.utcnow()
        entity.revocation_reason = reason
        db.session.commit()
        return self._to_domain(entity)

    def clear(self) -> None:
        db.session.execute(delete(IssuedCertificateEntity))
        db.session.commit()

    def _to_domain(self, entity: IssuedCertificateEntity) -> IssuedCertificate:
        certificate = x509.load_pem_x509_certificate(entity.certificate_pem.encode("utf-8"))
        return IssuedCertificate(
            kid=entity.kid,
            certificate=certificate,
            usage_type=UsageType(entity.usage_type),
            jwk=entity.jwk,
            issued_at=entity.issued_at,
            revoked_at=entity.revoked_at,
            revocation_reason=entity.revocation_reason,
        )
