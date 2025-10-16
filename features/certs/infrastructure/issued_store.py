"""発行済み証明書の永続化ストア"""
from __future__ import annotations

from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from core.db import db
from features.certs.domain.exceptions import CertificateNotFoundError
from features.certs.domain.models import CertificateGroup, IssuedCertificate, RotationPolicy
from features.certs.domain.usage import UsageType

from .models import CertificateGroupEntity, IssuedCertificateEntity


class IssuedCertificateStore:
    """SQLAlchemyを利用した証明書ストア"""

    def save(self, certificate: IssuedCertificate) -> IssuedCertificate:
        """証明書情報を保存する"""

        expires_at = None
        try:
            if hasattr(certificate.certificate, "not_valid_after_utc"):
                expires_at = certificate.certificate.not_valid_after_utc
            else:  # pragma: no cover - cryptography古いバージョン向けフォールバック
                expires_at = certificate.certificate.not_valid_after
        except Exception:  # pragma: no cover - 異常系
            expires_at = None

        pem = certificate.certificate.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        entity = IssuedCertificateEntity(
            kid=certificate.kid,
            usage_type=certificate.usage_type.value,
            group_id=certificate.group_id or (certificate.group.id if certificate.group else None),
            certificate_pem=pem,
            jwk=certificate.jwk,
            issued_at=certificate.issued_at,
            expires_at=expires_at,
            revoked_at=certificate.revoked_at,
            revocation_reason=certificate.revocation_reason,
            auto_rotated_from_kid=certificate.auto_rotated_from_kid,
        )
        entity = db.session.merge(entity)
        db.session.commit()
        db.session.refresh(entity)
        return self._entity_to_domain(entity)

    def list(
        self,
        usage_type: UsageType | None = None,
        *,
        group_code: str | None = None,
    ) -> list[IssuedCertificate]:
        """証明書一覧を取得する"""

        query = IssuedCertificateEntity.query.order_by(IssuedCertificateEntity.issued_at.desc())
        if usage_type is not None:
            query = query.filter_by(usage_type=usage_type.value)
        if group_code is not None:
            query = query.join(IssuedCertificateEntity.group).filter(
                CertificateGroupEntity.group_code == group_code
            )
        return [self._entity_to_domain(entity) for entity in query.all()]

    def find_latest_for_group(self, group_id: int) -> IssuedCertificate | None:
        entity = (
            IssuedCertificateEntity.query.filter_by(group_id=group_id)
            .order_by(IssuedCertificateEntity.issued_at.desc())
            .first()
        )
        return self._entity_to_domain(entity) if entity else None

    def count_active_in_group(self, group_id: int) -> int:
        now = datetime.utcnow()
        return (
            IssuedCertificateEntity.query.filter(
                IssuedCertificateEntity.group_id == group_id,
                IssuedCertificateEntity.revoked_at.is_(None),
                (IssuedCertificateEntity.expires_at.is_(None))
                | (IssuedCertificateEntity.expires_at > now),
            )
            .with_entities(IssuedCertificateEntity.kid)
            .count()
        )

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

    def list_jwks_for_group(self, group_code: str) -> list[dict]:
        """グループ単位のJWKS情報を取得する"""

        query = (
            IssuedCertificateEntity.query.join(IssuedCertificateEntity.group)
            .filter(
                CertificateGroupEntity.group_code == group_code,
                IssuedCertificateEntity.revoked_at.is_(None),
            )
            .order_by(IssuedCertificateEntity.issued_at.desc())
        )
        now = datetime.utcnow()
        jwks: list[dict] = []
        for entity in query.all():
            if entity.expires_at and entity.expires_at <= now:
                continue
            jwks.append(entity.jwk)
        return jwks

    def _entity_to_domain(self, entity: IssuedCertificateEntity | None) -> IssuedCertificate | None:
        if entity is None:
            return None
        certificate = x509.load_pem_x509_certificate(entity.certificate_pem.encode("utf-8"))
        group = self._convert_group(entity.group)
        return IssuedCertificate(
            kid=entity.kid,
            certificate=certificate,
            usage_type=UsageType(entity.usage_type),
            jwk=entity.jwk,
            issued_at=entity.issued_at,
            expires_at=entity.expires_at,
            revoked_at=entity.revoked_at,
            revocation_reason=entity.revocation_reason,
            group_id=entity.group_id,
            group=group,
            auto_rotated_from_kid=entity.auto_rotated_from_kid,
        )

    def _convert_group(self, entity: CertificateGroupEntity | None) -> CertificateGroup | None:
        if entity is None:
            return None
        rotation_policy = RotationPolicy(
            auto_rotate=entity.auto_rotate,
            rotation_threshold_days=entity.rotation_threshold_days,
        )
        return CertificateGroup(
            id=entity.id,
            group_code=entity.group_code,
            display_name=entity.display_name,
            rotation_policy=rotation_policy,
            usage_type=UsageType(entity.usage_type),
            key_type=entity.key_type,
            key_curve=entity.key_curve,
            key_size=entity.key_size,
            subject=entity.subject or {},
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


__all__ = ["IssuedCertificateStore"]
