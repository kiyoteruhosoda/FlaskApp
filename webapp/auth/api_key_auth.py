"""Authentication helpers for API key based service account access."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence

from flask import current_app, g, request

from core.models.service_account import ServiceAccount
from core.models.service_account_api_key import ServiceAccountApiKey
from webapp.services.service_account_api_key_service import (
    ServiceAccountApiKeyService,
)


API_KEY_SECURITY_SCHEME_NAME = "ServiceAccountApiKey"


@dataclass
class ApiKeyAuthError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - dataclass repr is enough
        return self.message


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _extract_api_key_token() -> str:
    header = request.headers.get("Authorization", "")
    if not header:
        raise ApiKeyAuthError("MissingAuthorization", "The Authorization header is missing.")
    if not header.startswith("ApiKey "):
        raise ApiKeyAuthError("InvalidAuthorization", "The Authorization header is not an API key.")
    token = header.split(" ", 1)[1].strip()
    if not token:
        raise ApiKeyAuthError("InvalidAuthorization", "The API key value is empty.")
    return token


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


def require_api_key_scopes(scopes: Sequence[str] | None):
    """Decorator to require API key authentication with optional scope enforcement."""

    def decorator(func):
        from functools import wraps

        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                token = _extract_api_key_token()
                key, account = ServiceAccountApiKeyAuthenticator.authenticate(
                    token, required_scopes=scopes
                )
            except ApiKeyAuthError as exc:
                current_app.logger.info(
                    "API key authentication failed.",
                    extra={
                        "event": "service_account_api_key.auth_failed",
                        "code": exc.code,
                        "error_message": exc.message,
                        "endpoint": request.path,
                    },
                )
                status = 403 if exc.code == "InsufficientScope" else 401
                response = {"error": exc.code, "message": exc.message}
                return response, status

            g.service_account = account
            g.service_account_api_key = key

            current_app.logger.debug(
                "API key authentication success.",
                extra={
                    "event": "service_account_api_key.auth_success",
                    "service_account": account.name,
                    "api_key_id": key.api_key_id,
                    "endpoint": request.path,
                    "scopes": list(scopes or []),
                },
            )

            ServiceAccountApiKeyService.record_usage(
                key,
                ip_address=request.remote_addr,
                endpoint=request.path,
                user_agent=request.headers.get("User-Agent"),
            )

            return func(*args, **kwargs)

        required_scopes = tuple(scope for scope in (scopes or []) if scope)

        wrapper._apidoc = deepcopy(getattr(wrapper, "_apidoc", {}))
        manual_doc = deepcopy(wrapper._apidoc.get("manual_doc", {}))

        security_requirement = {API_KEY_SECURITY_SCHEME_NAME: []}
        security = list(manual_doc.get("security", []))
        if security_requirement not in security:
            security.append(security_requirement)
        manual_doc["security"] = security
        manual_doc["x-required-scopes"] = list(required_scopes)
        manual_doc["x-requires-authentication"] = True

        wrapper._apidoc["manual_doc"] = manual_doc
        wrapper._required_api_key_scopes = required_scopes
        wrapper._requires_api_key_authentication = True
        wrapper._auth_enforced = True

        return wrapper

    return decorator


__all__ = [
    "ServiceAccountApiKeyAuthenticator",
    "ApiKeyAuthError",
    "require_api_key_scopes",
    "API_KEY_SECURITY_SCHEME_NAME",
]
