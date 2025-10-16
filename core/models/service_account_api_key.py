"""Models for service account API keys and their usage logs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List

from werkzeug.security import check_password_hash

from core.db import db

# Align BIGINT usage with other models to keep SQLite compatibility
BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ServiceAccountApiKey(db.Model):
    __tablename__ = "service_account_api_key"

    api_key_id = db.Column(BigInt, primary_key=True, autoincrement=True)
    service_account_id = db.Column(
        BigInt,
        db.ForeignKey("service_account.service_account_id"),
        nullable=False,
        index=True,
    )
    public_id = db.Column(db.String(32), nullable=False, unique=True)
    secret_hash = db.Column(db.String(255), nullable=False)
    scope_names = db.Column(db.String(2000), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.func.now(),
    )
    created_by = db.Column(db.String(255), nullable=False)

    service_account = db.relationship(
        "ServiceAccount",
        backref=db.backref(
            "api_keys",
            lazy="dynamic",
            cascade="all, delete-orphan",
        ),
    )

    def set_scopes(self, scopes: Iterable[str]) -> None:
        normalized: List[str] = []
        seen = set()
        for scope in scopes:
            if not scope:
                continue
            if scope in seen:
                continue
            normalized.append(scope)
            seen.add(scope)
        self.scope_names = " ".join(normalized)

    @property
    def scopes(self) -> List[str]:
        if not self.scope_names:
            return []
        return [
            scope
            for scope in (part.strip() for part in self.scope_names.split(" "))
            if scope
        ]

    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, reference: datetime | None = None) -> bool:
        if not self.expires_at:
            return False
        reference = reference or _utc_now()
        return self.expires_at <= reference

    def verify_secret(self, secret: str) -> bool:
        if not secret:
            return False
        return check_password_hash(self.secret_hash, secret)

    def as_dict(self) -> dict:
        return {
            "api_key_id": self.api_key_id,
            "service_account_id": self.service_account_id,
            "public_id": self.public_id,
            "scopes": " ".join(self.scopes),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
        }


class ServiceAccountApiKeyLog(db.Model):
    __tablename__ = "service_account_api_key_log"

    log_id = db.Column(BigInt, primary_key=True, autoincrement=True)
    api_key_id = db.Column(
        BigInt,
        db.ForeignKey("service_account_api_key.api_key_id"),
        nullable=False,
        index=True,
    )
    accessed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.func.now(),
    )
    ip_address = db.Column(db.String(64), nullable=True)
    endpoint = db.Column(db.String(255), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)

    api_key = db.relationship(
        "ServiceAccountApiKey",
        backref=db.backref(
            "access_logs",
            lazy="dynamic",
            cascade="all, delete-orphan",
        ),
    )

    def as_dict(self) -> dict:
        return {
            "log_id": self.log_id,
            "api_key_id": self.api_key_id,
            "accessed_at": self.accessed_at.isoformat() if self.accessed_at else None,
            "ip_address": self.ip_address,
            "endpoint": self.endpoint,
            "user_agent": self.user_agent,
        }


__all__ = [
    "ServiceAccountApiKey",
    "ServiceAccountApiKeyLog",
]
