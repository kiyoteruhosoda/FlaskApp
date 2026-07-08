"""Authentication helpers for API key based service account access (FastAPI version)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from shared.infrastructure.models.service_account import ServiceAccount
from shared.infrastructure.models.service_account_api_key import ServiceAccountApiKey
from shared.domain.auth.principal import AuthenticatedPrincipal
from presentation.fastapi.services.service_account_api_key_service import (
    ServiceAccountApiKeyService,
)

logger = logging.getLogger(__name__)

API_KEY_SECURITY_SCHEME_NAME = "ServiceAccountApiKey"


@dataclass
class ApiKeyAuthError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return self.message


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ServiceAccountApiKeyAuthenticator:
    """Validate API key tokens issued for service accounts."""

    @staticmethod
    def _select_key(token: str) -> ServiceAccountApiKey:
        parts = token.split("-", 2)
        if len(parts) != 3 or parts[0] != "sa":
            raise ApiKeyAuthError("InvalidFormat", "The API key format is invalid.")

        public_id, secret = parts[1], parts[2]
        if not public_id or not secret:
            raise ApiKeyAuthError("InvalidFormat", "The API key is incomplete.")

        key = ServiceAccountApiKey.query.filter_by(public_id=public_id).first()
        if not key:
            raise ApiKeyAuthError("UnknownKey", "The API key is not recognized.")

        if not key.verify_secret(secret):
            raise ApiKeyAuthError("InvalidSecret", "The API key secret is invalid.")

        return key

    @classmethod
    def authenticate(
        cls,
        token: str,
        *,
        required_scopes: Iterable[str] | None = None,
    ) -> tuple[ServiceAccountApiKey, ServiceAccount]:
        key = cls._select_key(token)
        account = key.service_account

        if not account or not account.active_flg:
            raise ApiKeyAuthError("DisabledAccount", "The service account is disabled.")

        if key.is_revoked():
            raise ApiKeyAuthError("Revoked", "The API key has been revoked.")

        if key.is_expired(_utc_now()):
            raise ApiKeyAuthError("Expired", "The API key has expired.")

        if required_scopes:
            scopes = set(scope for scope in required_scopes if scope)
            if scopes and not scopes.issubset(set(key.scopes)):
                raise ApiKeyAuthError(
                    "InsufficientScope",
                    "The API key does not include the required scopes.",
                )

        return key, account


def _resolve_api_key_account(api_key: str, *, required_scopes=None):
    """Resolve a service account from an API key string."""
    parts = api_key.split("-", 2)
    if len(parts) != 3 or parts[0] != "sa":
        raise ApiKeyAuthError("InvalidFormat", "The API key format is invalid.")
    public_id, secret = parts[1], parts[2]
    key = ServiceAccountApiKey.query.filter_by(public_id=public_id).first()
    if not key:
        raise ApiKeyAuthError("UnknownKey", "The API key is not recognized.")
    if not key.verify_secret(secret):
        raise ApiKeyAuthError("InvalidSecret", "The API key secret is invalid.")
    account = key.service_account
    if not account or not account.active_flg:
        raise ApiKeyAuthError("DisabledAccount", "The service account is disabled.")
    if key.is_revoked():
        raise ApiKeyAuthError("Revoked", "The API key has been revoked.")
    if key.is_expired(_utc_now()):
        raise ApiKeyAuthError("Expired", "The API key has expired.")
    if required_scopes:
        scopes = set(s for s in required_scopes if s)
        if scopes and not scopes.issubset(set(key.scopes)):
            raise ApiKeyAuthError("InsufficientScope", "The API key does not include the required scopes.")
    return account


__all__ = [
    "ServiceAccountApiKeyAuthenticator",
    "ApiKeyAuthError",
    "_resolve_api_key_account",
    "API_KEY_SECURITY_SCHEME_NAME",
]
