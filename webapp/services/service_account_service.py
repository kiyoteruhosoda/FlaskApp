"""Service layer for managing service accounts and their credentials."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from flask import current_app
from flask_babel import gettext as _
from sqlalchemy.exc import IntegrityError

from core.db import db
from core.models.service_account import ServiceAccount


@dataclass
class ServiceAccountValidationError(Exception):
    message: str
    field: str | None = None

    def __str__(self) -> str:  # pragma: no cover - dataclass will cover
        return self.message


class ServiceAccountNotFoundError(Exception):
    pass


class ServiceAccountService:
    allowed_algorithms = {"ES256", "RS256"}

    @staticmethod
    def _normalize_public_key(pem_text: str) -> str:
        if not pem_text or not pem_text.strip():
            raise ServiceAccountValidationError(
                _("Please provide a public key."), field="public_key"
            )

        text = pem_text.strip().encode("utf-8")
        if b"BEGIN PUBLIC KEY" not in text:
            header = b"-----BEGIN PUBLIC KEY-----\n"
            footer = b"\n-----END PUBLIC KEY-----"
            text = header + text.replace(b"\r", b"") + footer
        else:
            text = text.replace(b"\r", b"")

        try:
            key = load_pem_public_key(text)
        except Exception as exc:  # pragma: no cover - cryptography provides detailed error
            raise ServiceAccountValidationError(
                _("The public key is not a valid PEM-formatted value."),
                field="public_key",
            ) from exc

        if not isinstance(key, (EllipticCurvePublicKey, RSAPublicKey)):
            raise ServiceAccountValidationError(
                _("The provided public key type is not supported."),
                field="public_key",
            )

        normalized = key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        # 末尾の改行や余分な空白を除去し、統一した形式で保存
        lines = [line.strip() for line in normalized.decode("utf-8").strip().splitlines()]
        return "\n".join(lines)

    @staticmethod
    def _normalize_scopes(
        scopes: str | Sequence[str],
        *,
        allowed_scopes: Iterable[str] | None,
    ) -> List[str]:
        if isinstance(scopes, str):
            raw = [part.strip() for part in scopes.split(",")]
        else:
            raw = [str(part).strip() for part in scopes]

        normalized: List[str] = []
        seen = set()
        for scope in raw:
            if not scope:
                continue
            if scope in seen:
                continue
            normalized.append(scope)
            seen.add(scope)

        if allowed_scopes is not None:
            allowed_set = {scope.strip() for scope in allowed_scopes if scope}
            disallowed = [scope for scope in normalized if scope not in allowed_set]
            if disallowed:
                raise ServiceAccountValidationError(
                    _("You are not allowed to assign the specified scopes."),
                    field="scope_names",
                )

        return normalized

    @classmethod
    def create_account(
        cls,
        *,
        name: str,
        description: str | None,
        public_key: str,
        scope_names: str | Sequence[str],
        active: bool,
        allowed_scopes: Iterable[str] | None,
    ) -> ServiceAccount:
        if not name or not name.strip():
            raise ServiceAccountValidationError(
                _("Please provide a service account name."), field="name"
            )

        normalized_key = cls._normalize_public_key(public_key)
        normalized_scopes = cls._normalize_scopes(scope_names, allowed_scopes=allowed_scopes)

        account = ServiceAccount(
            name=name.strip(),
            description=description.strip() if description else None,
            public_key=normalized_key,
            active_flg=bool(active),
        )
        account.set_scopes(normalized_scopes)

        db.session.add(account)
        try:
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            raise ServiceAccountValidationError(
                _("A service account with the same name already exists."),
                field="name",
            ) from exc

        current_app.logger.info(
            "Service account created.",
            extra={
                "event": "service_account.created",
                "service_account": account.name,
                "active": account.active_flg,
                "scopes": normalized_scopes,
            },
        )
        return account

    @classmethod
    def update_account(
        cls,
        account_id: int,
        *,
        name: str,
        description: str | None,
        public_key: str,
        scope_names: str | Sequence[str],
        active: bool,
        allowed_scopes: Iterable[str] | None,
    ) -> ServiceAccount:
        account = ServiceAccount.query.get(account_id)
        if not account:
            raise ServiceAccountNotFoundError()

        if not name or not name.strip():
            raise ServiceAccountValidationError(
                _("Please provide a service account name."), field="name"
            )

        normalized_key = cls._normalize_public_key(public_key)
        normalized_scopes = cls._normalize_scopes(scope_names, allowed_scopes=allowed_scopes)

        account.name = name.strip()
        account.description = description.strip() if description else None
        account.public_key = normalized_key
        account.active_flg = bool(active)
        account.set_scopes(normalized_scopes)

        try:
            db.session.commit()
        except IntegrityError as exc:
            db.session.rollback()
            raise ServiceAccountValidationError(
                _("A service account with the same name already exists."),
                field="name",
            ) from exc

        current_app.logger.info(
            "Service account updated.",
            extra={
                "event": "service_account.updated",
                "service_account": account.name,
                "active": account.active_flg,
                "scopes": normalized_scopes,
            },
        )
        return account

    @staticmethod
    def delete_account(account_id: int) -> None:
        account = ServiceAccount.query.get(account_id)
        if not account:
            raise ServiceAccountNotFoundError()

        db.session.delete(account)
        db.session.commit()

        current_app.logger.info(
            "Service account deleted.",
            extra={
                "event": "service_account.deleted",
                "service_account": account.name,
            },
        )

    @staticmethod
    def list_accounts() -> list[ServiceAccount]:
        return ServiceAccount.query.order_by(ServiceAccount.name.asc()).all()

    @staticmethod
    def get_by_name(name: str) -> ServiceAccount | None:
        if not name:
            return None
        return ServiceAccount.query.filter_by(name=name).first()
