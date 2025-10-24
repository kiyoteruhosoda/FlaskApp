"""Service account model for JWT based machine authentication."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, List

from sqlalchemy.orm import DynamicMapped, Mapped, mapped_column, relationship

from core.db import db

# Align BIGINT usage with other models to keep SQLite compatibility
BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ServiceAccount(db.Model):
    __tablename__ = "service_account"

    service_account_id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(db.String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    certificate_group_code: Mapped[str | None] = mapped_column(
        db.String(64),
        db.ForeignKey("certificate_groups.group_code"),
        nullable=True,
    )
    scope_names: Mapped[str] = mapped_column(db.String(1000), nullable=False, default="")
    active_flg: Mapped[bool] = mapped_column(db.Boolean, nullable=False, default=True)
    reg_dttm: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.func.now(),
    )
    api_keys: DynamicMapped["ServiceAccountApiKey"] = relationship(
        "ServiceAccountApiKey",
        back_populates="service_account",
        cascade="all, delete-orphan",
    )
    mod_dttm: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
        server_default=db.func.now(),
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
        self.scope_names = ",".join(normalized)

    @property
    def scopes(self) -> List[str]:
        if not self.scope_names:
            return []
        return [scope for scope in (s.strip() for s in self.scope_names.split(",")) if scope]

    def is_active(self) -> bool:
        return bool(self.active_flg)

    def as_dict(self) -> dict[str, Any]:
        return {
            "service_account_id": self.service_account_id,
            "name": self.name,
            "description": self.description,
            "certificate_group_code": self.certificate_group_code,
            "scope_names": self.scope_names,
            "active_flg": self.active_flg,
            "reg_dttm": self.reg_dttm.isoformat() if self.reg_dttm else None,
            "mod_dttm": self.mod_dttm.isoformat() if self.mod_dttm else None,
        }


__all__ = ["ServiceAccount"]
