"""Service account model for JWT based machine authentication."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List

from core.db import db

# Align BIGINT usage with other models to keep SQLite compatibility
BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ServiceAccount(db.Model):
    __tablename__ = "service_account"

    service_account_id = db.Column(BigInt, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    public_key = db.Column(db.Text, nullable=False)
    scope_names = db.Column(db.String(1000), nullable=False, default="")
    active_flg = db.Column(db.Boolean, nullable=False, default=True)
    reg_dttm = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        server_default=db.func.now(),
    )
    mod_dttm = db.Column(
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

    def as_dict(self) -> dict:
        return {
            "service_account_id": self.service_account_id,
            "name": self.name,
            "description": self.description,
            "public_key": self.public_key,
            "scope_names": self.scope_names,
            "active_flg": self.active_flg,
            "reg_dttm": self.reg_dttm.isoformat() if self.reg_dttm else None,
            "mod_dttm": self.mod_dttm.isoformat() if self.mod_dttm else None,
        }


__all__ = ["ServiceAccount"]
