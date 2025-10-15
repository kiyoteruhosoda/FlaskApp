"""Authentication helpers for validating service account JWTs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Sequence

import json
import jwt
import requests
from flask import current_app, g, request
from flask_babel import gettext as _
from jwt import algorithms as jwt_algorithms

from core.models.service_account import ServiceAccount
from webapp.services.service_account_service import ServiceAccountService

_ALLOWED_ALGORITHMS = {"ES256", "RS256"}
_MAX_TOKEN_LIFETIME = timedelta(minutes=10)


@dataclass
class ServiceAccountJWTError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - dataclass repr is enough
        return self.message


class ServiceAccountTokenValidator:
    """Verify JWT signed tokens issued by registered service accounts."""

    @staticmethod
    def _load_signing_key(account: ServiceAccount, kid: str, algorithm: str):
        if not kid:
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("The token does not specify a key identifier."),
            )

        if not account.jtk_endpoint:
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("The service account is missing a JTK endpoint."),
            )

        timeout = current_app.config.get("SERVICE_ACCOUNT_JWKS_TIMEOUT", 5)
        try:
            response = requests.get(account.jtk_endpoint, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("Failed to retrieve the signing keys."),
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("The JTK endpoint returned invalid JSON."),
            ) from exc

        keys = payload.get("keys")
        if not isinstance(keys, list):
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("The JTK endpoint response did not include signing keys."),
            )

        for jwk in keys:
            if jwk.get("kid") != kid:
                continue
            try:
                jwk_payload = json.dumps(jwk)
                if algorithm.startswith("RS"):
                    return jwt_algorithms.RSAAlgorithm.from_jwk(jwk_payload)
                if algorithm.startswith("ES"):
                    return jwt_algorithms.ECAlgorithm.from_jwk(jwk_payload)
            except (ValueError, TypeError) as exc:
                raise ServiceAccountJWTError(
                    "InvalidSignature",
                    _("Failed to construct a signing key from the JTK response."),
                ) from exc

        raise ServiceAccountJWTError(
            "InvalidSignature",
            _("Failed to find a matching signing key."),
        )

    @staticmethod
    def _select_account(claims: dict) -> ServiceAccount:
        account_name = claims.get("iss") or claims.get("sub")
        if not account_name:
            raise ServiceAccountJWTError(
                "UnknownAccount",
                _("The service account identifier is missing from the token."),
            )

        account = ServiceAccountService.get_by_name(account_name)
        if not account:
            raise ServiceAccountJWTError(
                "UnknownAccount",
                _("The service account is not registered."),
            )
        if not account.active_flg:
            raise ServiceAccountJWTError(
                "DisabledAccount",
                _("The service account is disabled."),
            )
        return account

    @classmethod
    def verify(
        cls,
        token: str,
        *,
        audience: str | Sequence[str] | None,
        required_scopes: Iterable[str] | None = None,
    ) -> tuple[ServiceAccount, dict]:
        if not token:
            raise ServiceAccountJWTError(
                "UnknownAccount",
                _("The token is not provided."),
            )

        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("The JWT header is invalid."),
            ) from exc

        algorithm = header.get("alg")
        if algorithm not in _ALLOWED_ALGORITHMS:
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("The signature algorithm is not supported."),
            )

        try:
            unsigned_claims = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False, "verify_aud": False},
                algorithms=[algorithm],
            )
        except jwt.InvalidTokenError as exc:
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("Failed to parse the JWT."),
            ) from exc

        account = cls._select_account(unsigned_claims)
        kid = header.get("kid")
        signing_key = cls._load_signing_key(account, kid, algorithm)

        try:
            claims = jwt.decode(
                token,
                key=signing_key,
                algorithms=[algorithm],
                audience=audience,
                options={"require": ["iat", "exp"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise ServiceAccountJWTError(
                "ExpiredToken",
                _("The token has expired."),
            ) from exc
        except jwt.InvalidAudienceError as exc:
            raise ServiceAccountJWTError(
                "InvalidAudience",
                _("The audience does not match."),
            ) from exc
        except jwt.InvalidSignatureError as exc:
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("Failed to verify the signature."),
            ) from exc
        except jwt.InvalidTokenError as exc:
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("The JWT is invalid."),
            ) from exc

        issued_at = datetime.fromtimestamp(claims["iat"], timezone.utc)
        expires_at = datetime.fromtimestamp(claims["exp"], timezone.utc)
        if expires_at <= issued_at:
            raise ServiceAccountJWTError(
                "ExpiredToken",
                _("The token lifetime is invalid."),
            )
        if expires_at - issued_at > _MAX_TOKEN_LIFETIME:
            raise ServiceAccountJWTError(
                "ExpiredToken",
                _("The token lifetime exceeds the maximum allowed."),
            )

        now = datetime.now(timezone.utc)
        if issued_at - now > timedelta(minutes=1):  # clock skew guard
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("The token issue time is in the future."),
            )

        account_scopes = set(account.scopes)
        if required_scopes:
            missing = [scope for scope in required_scopes if scope not in account_scopes]
            if missing:
                raise ServiceAccountJWTError(
                    "InvalidScope",
                    _("The required scope is not granted."),
                )

        return account, claims


def _extract_bearer_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return None


def require_service_account_scopes(
    scopes: Sequence[str] | None,
    *,
    audience: str | Sequence[str] | Callable[[object], str | Sequence[str]],
):
    """Decorator to protect endpoints that require service account authentication."""

    def decorator(func):
        from functools import wraps

        @wraps(func)
        def wrapper(*args, **kwargs):
            token = _extract_bearer_token()
            if callable(audience):
                resolved_audience = audience(request)
            else:
                resolved_audience = audience

            try:
                account, claims = ServiceAccountTokenValidator.verify(
                    token,
                    audience=resolved_audience,
                    required_scopes=scopes,
                )
            except ServiceAccountJWTError as exc:
                current_app.logger.info(
                    "Service account authentication failed.",
                    extra={
                        "event": "service_account.auth_failed",
                        "code": exc.code,
                        "message": exc.message,
                        "endpoint": request.path,
                    },
                )
                status = 401 if exc.code in {"InvalidSignature", "ExpiredToken"} else 403
                response = {
                    "error": exc.code,
                    "message": exc.message,
                }
                return response, status

            g.service_account = account
            g.service_account_claims = claims

            current_app.logger.debug(
                "Service account authentication success.",
                extra={
                    "event": "service_account.auth_success",
                    "service_account": account.name,
                    "endpoint": request.path,
                    "scopes": list(scopes or []),
                },
            )
            return func(*args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "ServiceAccountTokenValidator",
    "ServiceAccountJWTError",
    "require_service_account_scopes",
]
