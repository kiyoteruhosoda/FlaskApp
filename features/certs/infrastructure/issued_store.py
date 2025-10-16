"""発行済み証明書の永続化ストア"""
from __future__ import annotations

from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from core.db import db
from features.certs.domain.exceptions import CertificateNotFoundError
from features.certs.domain.models import IssuedCertificate
from features.certs.domain.usage import UsageType

from .models import IssuedCertificateEntity


class IssuedCertificateStore:
    """SQLAlchemyを利用した証明書ストア"""

    def save(self, certificate: IssuedCertificate) -> None:
        """証明書情報を保存する"""
        entity = IssuedCertificateEntity(
            kid=certificate.kid,
            usage_type=certificate.usage_type.value,
            certificate_pem=certificate.certificate.public_bytes(
                serialization.Encoding.PEM
            ).decode("utf-8"),
            jwk=certificate.jwk,
            issued_at=certificate.issued_at,
            revoked_at=certificate.revoked_at,
            revocation_reason=certificate.revocation_reason,
        )
        db.session.merge(entity)
        db.session.commit()

    def list(self, usage_type: UsageType | None = None) -> list[IssuedCertificate]:
        """証明書一覧を取得する"""
        query = IssuedCertificateEntity.query.order_by(IssuedCertificateEntity.issued_at.desc())
        if usage_type is not None:
            query = query.filter_by(usage_type=usage_type.value)
        return [self._entity_to_domain(entity) for entity in query.all()]

    def get(self, kid: str) -> IssuedCertificate:
        """証明書詳細を取得する"""
        entity = db.session.get(IssuedCertificateEntity, kid)
        if entity is None:
            raise CertificateNotFoundError("指定された証明書が見つかりません")
        return self._entity_to_domain(entity)

    def revoke(self, kid: str, reason: str | None = None) -> IssuedCertificate:
        """証明書を失効させる"""
        entity = db.session.get(IssuedCertificateEntity, kid)
        if entity is None:
            raise CertificateNotFoundError("指定された証明書が見つかりません")
        entity.revoked_at = datetime.utcnow()
        entity.revocation_reason = reason
        db.session.commit()
        return self._entity_to_domain(entity)

    def list_jwks(self, usage_type: UsageType) -> list[dict]:
        """JWKS情報を取得する"""
        query = (
            IssuedCertificateEntity.query.filter_by(usage_type=usage_type.value)
            .order_by(IssuedCertificateEntity.issued_at.desc())
        )
        return [entity.jwk for entity in query.all()]

    def _entity_to_domain(self, entity: IssuedCertificateEntity) -> IssuedCertificate:
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


__all__ = ["IssuedCertificateStore"]
