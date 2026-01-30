"""証明書秘密鍵の保存を担当するストア"""
from __future__ import annotations

from datetime import datetime

from core.db import db
from bounded_contexts.certs.domain.exceptions import CertificatePrivateKeyNotFoundError
from bounded_contexts.certs.domain.models import CertificatePrivateKey

from .models import CertificatePrivateKeyEntity


class CertificatePrivateKeyStore:
    """発行済み証明書に紐づく秘密鍵を保存・取得するストア"""

    def save(
        self,
        *,
        kid: str,
        private_key_pem: str,
        group_id: int | None,
        expires_at: datetime | None = None,
    ) -> CertificatePrivateKey:
        entity = CertificatePrivateKeyEntity(
            kid=kid,
            group_id=group_id,
            private_key_pem=private_key_pem,
            expires_at=expires_at,
        )
        entity = db.session.merge(entity)
        db.session.commit()
        db.session.refresh(entity)
        return self._entity_to_domain(entity)

    def get(self, kid: str) -> CertificatePrivateKey:
        entity = db.session.get(CertificatePrivateKeyEntity, kid)
        if entity is None:
            raise CertificatePrivateKeyNotFoundError("証明書に対応する秘密鍵が見つかりません")
        return self._entity_to_domain(entity)

    def delete(self, kid: str) -> None:
        entity = db.session.get(CertificatePrivateKeyEntity, kid)
        if entity is None:
            return
        db.session.delete(entity)
        db.session.commit()

    def _entity_to_domain(self, entity: CertificatePrivateKeyEntity) -> CertificatePrivateKey:
        return CertificatePrivateKey(
            kid=entity.kid,
            private_key_pem=entity.private_key_pem,
            group_id=entity.group_id,
            created_at=entity.created_at,
            expires_at=entity.expires_at,
        )


__all__ = ["CertificatePrivateKeyStore"]
