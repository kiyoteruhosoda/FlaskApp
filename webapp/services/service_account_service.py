"""Service layer for managing service accounts and their credentials."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from flask import current_app
from flask_babel import gettext as _
from sqlalchemy.exc import IntegrityError

from core.db import db
from core.models.service_account import ServiceAccount
from features.certs.application.use_cases import GetCertificateGroupUseCase
from features.certs.domain.exceptions import CertificateGroupNotFoundError
from features.certs.domain.models import CertificateGroup
from features.certs.domain.usage import UsageType


@dataclass
class ServiceAccountValidationError(Exception):
    message: str
    field: str | None = None

    def __str__(self) -> str:  # pragma: no cover - dataclass will cover
        return self.message


class ServiceAccountNotFoundError(Exception):
    pass


class ServiceAccountService:
    @staticmethod
    def _resolve_certificate_group(group_code: str) -> CertificateGroup:
        if not group_code or not group_code.strip():
            raise ServiceAccountValidationError(
                _("Please select a certificate group."),
                field="certificate_group_code",
            )

        code = group_code.strip()

        try:
            group = GetCertificateGroupUseCase().execute(code)
        except CertificateGroupNotFoundError as exc:
            raise ServiceAccountValidationError(
                _("The specified certificate group could not be found."),
                field="certificate_group_code",
            ) from exc

        if group.usage_type != UsageType.CLIENT_SIGNING:
            raise ServiceAccountValidationError(
                _("The certificate group must be configured for client signing."),
                field="certificate_group_code",
            )

        return group

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
        certificate_group_code: str,
        scope_names: str | Sequence[str],
        active: bool,
        allowed_scopes: Iterable[str] | None,
    ) -> ServiceAccount:
        if not name or not name.strip():
            raise ServiceAccountValidationError(
                _("Please provide a service account name."), field="name"
            )

        group = cls._resolve_certificate_group(certificate_group_code)
        normalized_scopes = cls._normalize_scopes(scope_names, allowed_scopes=allowed_scopes)

        account = ServiceAccount(
            name=name.strip(),
            description=description.strip() if description else None,
            certificate_group_code=group.group_code,
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
                "certificate_group": group.group_code,
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
        certificate_group_code: str,
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

        group = cls._resolve_certificate_group(certificate_group_code)
        normalized_scopes = cls._normalize_scopes(scope_names, allowed_scopes=allowed_scopes)

        account.name = name.strip()
        account.description = description.strip() if description else None
        account.certificate_group_code = group.group_code
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
                "certificate_group": group.group_code,
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
