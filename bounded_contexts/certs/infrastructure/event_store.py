"""証明書操作の監査ログストア"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from core.db import db
from bounded_contexts.certs.domain.models import CertificateEvent

from .models import CertificateEventEntity


class CertificateEventStore:
    """証明書操作の監査イベントを永続化するストア"""

    def record(
        self,
        *,
        actor: str,
        action: str,
        target_kid: str | None = None,
        target_group_code: str | None = None,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> CertificateEvent:
        occurred_at = occurred_at or datetime.utcnow()
        entity = CertificateEventEntity(
            actor=actor,
            action=action,
            target_kid=target_kid,
            target_group_code=target_group_code,
            reason=reason,
            details=details,
            occurred_at=occurred_at,
        )
        db.session.add(entity)
        db.session.commit()
        db.session.refresh(entity)
        return self._entity_to_domain(entity)

    def _entity_to_domain(self, entity: CertificateEventEntity) -> CertificateEvent:
        return CertificateEvent(
            id=entity.id,
            actor=entity.actor,
            action=entity.action,
            target_kid=entity.target_kid,
            target_group_code=entity.target_group_code,
            reason=entity.reason,
            details=entity.details or None,
            occurred_at=entity.occurred_at,
        )


__all__ = ["CertificateEventStore"]
