"""Models for service account API keys and their usage logs."""
from __future__ import annotations
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List

from sqlalchemy.orm import DynamicMapped, Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash

from core.db import db

# Align BIGINT usage with other models to keep SQLite compatibility
BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ServiceAccountApiKey(db.Model):
    __tablename__ = "service_account_api_key"

    api_key_id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    service_account_id: Mapped[int] = mapped_column(
        BigInt,
        db.ForeignKey("service_account.service_account_id"),
        nullable=False,
        index=True,
    )
    public_id: Mapped[str] = mapped_column(db.String(32), nullable=False, unique=True)
    secret_hash: Mapped[str] = mapped_column(db.String(255), nullable=False)
    scope_names: Mapped[str] = mapped_column(db.String(2000), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(db.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.func.now(),
    )
    created_by: Mapped[str] = mapped_column(db.String(255), nullable=False)

    service_account: Mapped["ServiceAccount"] = relationship(
        "ServiceAccount",
        back_populates="api_keys",
    )
    access_logs: DynamicMapped["ServiceAccountApiKeyLog"] = relationship(
        "ServiceAccountApiKeyLog",
        back_populates="api_key",
        cascade="all, delete-orphan",
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

    def as_dict(self) -> dict[str, str | int | None]:
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

    log_id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    api_key_id: Mapped[int] = mapped_column(
        BigInt,
        db.ForeignKey("service_account_api_key.api_key_id"),
        nullable=False,
        index=True,
    )
    accessed_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.func.now(),
    )
    ip_address: Mapped[str | None] = mapped_column(db.String(64), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(db.String(255), nullable=True)

    api_key: Mapped[ServiceAccountApiKey] = relationship(
        "ServiceAccountApiKey",
        back_populates="access_logs",
    )

    def as_dict(self) -> dict[str, str | int | None]:
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
