"""Service layer for managing service account API keys."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence
import secrets

from flask import current_app
from werkzeug.security import generate_password_hash

from core.db import db
from core.models.service_account import ServiceAccount
from core.models.service_account_api_key import (
    ServiceAccountApiKey,
    ServiceAccountApiKeyLog,
)


@dataclass
class ServiceAccountApiKeyValidationError(Exception):
    message: str
    field: str | None = None

    def __str__(self) -> str:  # pragma: no cover - dataclass repr is enough
        return self.message


class ServiceAccountApiKeyNotFoundError(Exception):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ServiceAccountApiKeyService:
    @staticmethod
    def _normalize_scopes(scopes: str | Sequence[str]) -> list[str]:
        if isinstance(scopes, str):
            raw = [part.strip() for part in scopes.replace(",", " ").split(" ")]
        else:
            raw = [str(part).strip() for part in scopes]

        normalized: list[str] = []
        seen = set()
        for scope in raw:
            if not scope:
                continue
            if scope in seen:
                continue
            normalized.append(scope)
            seen.add(scope)
        return normalized

    @staticmethod
    def _ensure_account(account_id: int) -> ServiceAccount:
        account = db.session.get(ServiceAccount, account_id)
        if not account:
            raise ServiceAccountApiKeyNotFoundError()
        if not account.active_flg:
            raise ServiceAccountApiKeyValidationError(
                "The service account is disabled.",
                field=None,
            )
        return account

    @classmethod
    def create_key(
        cls,
        account_id: int,
        *,
        scopes: str | Sequence[str],
        expires_at: datetime | None,
        created_by: str,
    ) -> tuple[ServiceAccountApiKey, str]:
        account = cls._ensure_account(account_id)
        normalized_scopes = cls._normalize_scopes(scopes)
        if not normalized_scopes:
            raise ServiceAccountApiKeyValidationError(
                "At least one scope must be specified.", field="scopes"
            )

        allowed_scopes = set(account.scopes)
        requested_set = set(normalized_scopes)
        if not requested_set.issubset(allowed_scopes):
            raise ServiceAccountApiKeyValidationError(
                "The requested scopes are not permitted for this service account.",
                field="scopes",
            )

        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at <= _utc_now():
            raise ServiceAccountApiKeyValidationError(
                "The expiration time must be in the future.", field="expires_at"
            )

        if not created_by:
            raise ServiceAccountApiKeyValidationError(
                "The creator must be specified.", field="created_by"
            )

        # Generate a unique public identifier for the key
        public_id = None
        for _ in range(5):
            candidate = secrets.token_hex(8)
            existing = ServiceAccountApiKey.query.filter_by(public_id=candidate).first()
            if not existing:
                public_id = candidate
                break
        if public_id is None:
            raise RuntimeError("Failed to allocate a unique API key identifier.")

        secret = secrets.token_hex(24)
        api_key_value = f"sa-{public_id}-{secret}"

        record = ServiceAccountApiKey(
            service_account_id=account.service_account_id,
            public_id=public_id,
            secret_hash=generate_password_hash(secret),
            expires_at=expires_at,
            created_by=created_by,
        )
        record.set_scopes(normalized_scopes)

        db.session.add(record)
        db.session.commit()

        current_app.logger.info(
            "Service account API key created.",
            extra={
                "event": "service_account_api_key.created",
                "service_account": account.name,
                "api_key_id": record.api_key_id,
                "scopes": normalized_scopes,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "created_by": created_by,
            },
        )

        return record, api_key_value

    @classmethod
    def list_keys(cls, account_id: int) -> list[ServiceAccountApiKey]:
        cls._ensure_account(account_id)
        return (
            ServiceAccountApiKey.query.filter_by(service_account_id=account_id)
            .order_by(ServiceAccountApiKey.created_at.desc())
            .all()
        )

    @classmethod
    def revoke_key(
        cls, account_id: int, key_id: int, *, actor: str | None = None
    ) -> ServiceAccountApiKey:
        cls._ensure_account(account_id)
        key = (
            ServiceAccountApiKey.query.filter_by(
                service_account_id=account_id, api_key_id=key_id
            ).first()
        )
        if not key:
            raise ServiceAccountApiKeyNotFoundError()
        if key.revoked_at:
            return key

        key.revoked_at = _utc_now()
        db.session.commit()

        current_app.logger.info(
            "Service account API key revoked.",
            extra={
                "event": "service_account_api_key.revoked",
                "service_account_id": account_id,
                "api_key_id": key_id,
                "actor": actor,
            },
        )
        return key

    @classmethod
    def record_usage(
        cls,
        api_key: ServiceAccountApiKey,
        *,
        ip_address: str | None,
        endpoint: str | None,
        user_agent: str | None,
    ) -> ServiceAccountApiKeyLog:
        log = ServiceAccountApiKeyLog(
            api_key_id=api_key.api_key_id,
            ip_address=ip_address[:64] if ip_address else None,
            endpoint=endpoint[:255] if endpoint else None,
            user_agent=user_agent[:255] if user_agent else None,
        )
        db.session.add(log)
        db.session.commit()
        return log

    @classmethod
    def list_logs(
        cls,
        account_id: int,
        *,
        key_id: int | None = None,
        limit: int | None = 100,
    ) -> list[ServiceAccountApiKeyLog]:
        cls._ensure_account(account_id)
        query = ServiceAccountApiKeyLog.query.join(ServiceAccountApiKey).filter(
            ServiceAccountApiKey.service_account_id == account_id
        )
        if key_id is not None:
            query = query.filter(ServiceAccountApiKeyLog.api_key_id == key_id)

        query = query.order_by(ServiceAccountApiKeyLog.accessed_at.desc())

        if limit is not None:
            limit = max(1, min(limit, 500))
            query = query.limit(limit)

        return query.all()


__all__ = [
    "ServiceAccountApiKeyService",
    "ServiceAccountApiKeyValidationError",
    "ServiceAccountApiKeyNotFoundError",
]
