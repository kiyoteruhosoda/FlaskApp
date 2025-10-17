"""証明書グループを管理するストア"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from core.db import db
from sqlalchemy import func

from features.certs.domain.exceptions import (
    CertificateGroupConflictError,
    CertificateGroupNotFoundError,
)
from features.certs.domain.models import CertificateGroup, RotationPolicy
from features.certs.domain.usage import UsageType

from .models import CertificateGroupEntity, IssuedCertificateEntity


class CertificateGroupStore:
    """証明書グループのCRUDおよび検索"""

    def list_all(self) -> list[CertificateGroup]:
        entities = CertificateGroupEntity.query.order_by(CertificateGroupEntity.id.asc()).all()
        return [self._entity_to_domain(entity) for entity in entities]

    def list_auto_rotating(self) -> list[CertificateGroup]:
        entities = (
            CertificateGroupEntity.query.filter_by(auto_rotate=True)
            .order_by(CertificateGroupEntity.id.asc())
            .all()
        )
        return [self._entity_to_domain(entity) for entity in entities]

    def get_by_code(self, group_code: str) -> CertificateGroup:
        entity = CertificateGroupEntity.query.filter_by(group_code=group_code).first()
        if entity is None:
            raise CertificateGroupNotFoundError(f"グループが見つかりません: {group_code}")
        return self._entity_to_domain(entity)

    def get_by_id(self, group_id: int) -> CertificateGroup:
        entity = db.session.get(CertificateGroupEntity, group_id)
        if entity is None:
            raise CertificateGroupNotFoundError(f"グループが見つかりません: {group_id}")
        return self._entity_to_domain(entity)

    def create(self, group: CertificateGroup) -> CertificateGroup:
        existing = CertificateGroupEntity.query.filter_by(group_code=group.group_code).first()
        if existing is not None:
            raise CertificateGroupConflictError(
                f"グループコードが重複しています: {group.group_code}"
            )
        entity = self._upsert_entity(group)
        db.session.add(entity)
        db.session.commit()
        db.session.refresh(entity)
        return self._entity_to_domain(entity)

    def update(self, group: CertificateGroup) -> CertificateGroup:
        if not group.id:
            stored = CertificateGroupEntity.query.filter_by(group_code=group.group_code).first()
            if stored is None:
                raise CertificateGroupNotFoundError(
                    f"グループが見つかりません: {group.group_code}"
                )
            group = CertificateGroup(
                id=stored.id,
                group_code=group.group_code,
                display_name=group.display_name,
                rotation_policy=group.rotation_policy,
                usage_type=group.usage_type,
                key_type=group.key_type,
                key_curve=group.key_curve,
                key_size=group.key_size,
                subject=group.subject_dict(),
                created_at=stored.created_at,
                updated_at=stored.updated_at,
            )
        entity = self._upsert_entity(group)
        db.session.add(entity)
        db.session.commit()
        db.session.refresh(entity)
        return self._entity_to_domain(entity)

    def bulk_save(self, groups: Iterable[CertificateGroup]) -> list[CertificateGroup]:
        entities = [self._upsert_entity(group) for group in groups]
        db.session.add_all(entities)
        db.session.commit()
        for entity in entities:
            db.session.refresh(entity)
        return [self._entity_to_domain(entity) for entity in entities]

    def delete(self, group_code: str) -> None:
        entity = CertificateGroupEntity.query.filter_by(group_code=group_code).first()
        if entity is None:
            raise CertificateGroupNotFoundError(f"グループが見つかりません: {group_code}")
        active_certificates = (
            db.session.query(func.count())
            .select_from(IssuedCertificateEntity)
            .filter(
                IssuedCertificateEntity.group_id == entity.id,
                IssuedCertificateEntity.revoked_at.is_(None),
                (
                    IssuedCertificateEntity.expires_at.is_(None)
                    | (IssuedCertificateEntity.expires_at > datetime.utcnow())
                ),
            )
            .scalar()
        )
        if active_certificates:
            raise CertificateGroupConflictError(
                "有効な証明書が存在するためグループを削除できません"
            )
        db.session.delete(entity)
        db.session.commit()

    def _upsert_entity(self, group: CertificateGroup) -> CertificateGroupEntity:
        entity: CertificateGroupEntity | None = None
        if group.id:
            entity = db.session.get(CertificateGroupEntity, group.id)
        if entity is None:
            entity = CertificateGroupEntity()

        entity.group_code = group.group_code
        entity.display_name = group.display_name
        entity.auto_rotate = group.rotation_policy.auto_rotate
        entity.rotation_threshold_days = group.rotation_policy.rotation_threshold_days
        entity.key_type = group.key_type
        entity.key_curve = group.key_curve
        entity.key_size = group.key_size
        entity.subject = group.subject_dict()
        entity.usage_type = group.usage_type.value
        return entity

    def _entity_to_domain(self, entity: CertificateGroupEntity) -> CertificateGroup:
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


__all__ = ["CertificateGroupStore"]
