"""Authentication helpers for validating service account JWTs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Sequence
import uuid

import json
import jwt
from flask import current_app, g, request
from core.settings import settings
from flask_babel import gettext as _
from jwt import algorithms as jwt_algorithms
import redis
from redis import RedisError

from core.models.service_account import ServiceAccount
from shared.domain.auth.principal import AuthenticatedPrincipal
from webapp.services.service_account_service import ServiceAccountService
from bounded_contexts.certs.application.use_cases import ListJwksUseCase
from bounded_contexts.certs.domain.exceptions import CertificateGroupNotFoundError

_ALLOWED_ALGORITHMS = {"ES256", "RS256"}
_MAX_TOKEN_LIFETIME = timedelta(minutes=10)
_MAX_JTI_TTL_SECONDS = 600


@dataclass
class ServiceAccountJWTError(Exception):
    code: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - dataclass repr is enough
        return self.message


class _ServiceAccountJTIStore:
    """Replay protection for service account JWT IDs using Redis."""

    _KEY_PREFIX = "jti:"

    @staticmethod
    def _get_client():
        redis_url = settings.redis_url
        if not redis_url:
            raise ServiceAccountJWTError(
                "JTICheckFailed",
                _("Replay protection storage is not configured."),
            )

        try:
            return redis.from_url(redis_url)
        except RedisError as exc:
            raise ServiceAccountJWTError(
                "JTICheckFailed",
                _("Failed to connect to the replay protection storage."),
            ) from exc

    @classmethod
    def mark_as_used(
        cls,
        jti_value: object,
        issued_at: datetime,
        expires_at: datetime,
    ) -> None:
        if not settings.redis_url:
            # Replay保護ストレージが未設定の場合はJTI検証をスキップし、後続処理を継続する
            return

        if not isinstance(jti_value, str) or not jti_value.strip():
            raise ServiceAccountJWTError(
                "MissingJTI",
                _("The token must include a \"jti\" claim."),
            )

        try:
            parsed_jti = uuid.UUID(jti_value)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ServiceAccountJWTError(
                "InvalidJTI",
                _("The token \"jti\" claim must be a valid UUID."),
            ) from exc

        key = f"{cls._KEY_PREFIX}{parsed_jti}"  # store normalized UUID string

        ttl_seconds = int((expires_at - issued_at).total_seconds())
        if ttl_seconds <= 0:
            ttl_seconds = 1
        ttl_seconds = min(ttl_seconds, _MAX_JTI_TTL_SECONDS)

        client = cls._get_client()

        try:
            stored = client.set(key, "used", ex=ttl_seconds, nx=True)
            if not stored:
                raise ServiceAccountJWTError(
                    "ReplayDetected",
                    _("The token has already been used."),
                )
        except RedisError as exc:
            raise ServiceAccountJWTError(
                "JTICheckFailed",
                _("Failed to store the token identifier."),
            ) from exc


class ServiceAccountTokenValidator:
    """Verify JWT signed tokens issued by registered service accounts."""

    @staticmethod
    def _load_signing_key(account: ServiceAccount, kid: str, algorithm: str):
        if not kid:
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("The token does not specify a key identifier."),
            )

        if not account.certificate_group_code:
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("The service account is missing a certificate group."),
            )

        try:
            payload = ListJwksUseCase().execute(account.certificate_group_code)
        except CertificateGroupNotFoundError as exc:
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("The configured certificate group could not be found."),
            ) from exc

        keys = payload.get("keys")
        if not isinstance(keys, list):
            raise ServiceAccountJWTError(
                "InvalidSignature",
                _("No signing keys are registered for the certificate group."),
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
                    _("Failed to construct a signing key from the certificate group keys."),
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

        jti_value = claims.get("jti")
        _ServiceAccountJTIStore.mark_as_used(jti_value, issued_at, expires_at)

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

def _combine_allowed_audiences(
    candidate: str | Sequence[str] | None,
) -> str | list[str] | None:
    """Merge dynamic and configured audience values."""

    configured = settings.service_account_signing_audiences
    raw_env = settings._env.get("SERVICE_ACCOUNT_SIGNING_AUDIENCE")  # type: ignore[attr-defined]
    if raw_env:
        if isinstance(raw_env, str):
            env_values = [segment.strip() for segment in raw_env.split(",")]
        else:
            env_values = [str(raw_env)]
    else:
        env_values = []

    def _append(values: list[str], value: object | None) -> None:
        if value is None:
            return
        if isinstance(value, str):
            text = value.strip()
        else:
            text = str(value).strip()
        if not text:
            return
        if text not in values:
            values.append(text)

    allowed: list[str] = []

    if isinstance(candidate, (list, tuple, set)):
        for item in candidate:
            _append(allowed, item)
    else:
        _append(allowed, candidate)

    for item in configured:
        _append(allowed, item)

    for item in env_values:
        _append(allowed, item)

    if not allowed:
        return None
    if len(allowed) == 1:
        return allowed[0]
    return allowed


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

            merged_audience = _combine_allowed_audiences(resolved_audience)

            try:
                account, claims = ServiceAccountTokenValidator.verify(
                    token,
                    audience=merged_audience,
                    required_scopes=scopes,
                )
            except ServiceAccountJWTError as exc:
                current_app.logger.info(
                    "Service account authentication failed.",
                    extra={
                        "event": "service_account.auth_failed",
                        "code": exc.code,
                        "error_message": exc.message,
                        "endpoint": request.path,
                    },
                )
                if exc.code in {"InvalidSignature", "ExpiredToken"}:
                    status = 401
                elif exc.code in {"MissingJTI", "InvalidJTI", "ReplayDetected"}:
                    status = 400
                elif exc.code == "JTICheckFailed":
                    status = 500
                else:
                    status = 403
                response = {
                    "error": exc.code,
                    "message": exc.message,
                }
                return response, status

            g.service_account = account
            g.service_account_claims = claims

            scope_value = claims.get("scope", "") if isinstance(claims, dict) else ""
            if isinstance(scope_value, str):
                scope_items = {item for item in scope_value.split() if item}
            elif isinstance(scope_value, (list, tuple, set)):
                scope_items = {str(item) for item in scope_value if item}
            else:
                scope_items = set()

            g.current_token_scope = scope_items
            principal = AuthenticatedPrincipal.from_service_account(
                account, scope=scope_items
            )
            g.current_user = principal

            current_app.logger.debug(
                "Service account authentication success.",
                extra={
                    "event": "service_account.auth_success",
                    "service_account": principal.display_name,
                    "endpoint": request.path,
                    "scopes": list(scopes or []),
                },
            )
            return func(*args, **kwargs)

        wrapper._auth_enforced = True
        return wrapper

    return decorator


__all__ = [
    "ServiceAccountTokenValidator",
    "ServiceAccountJWTError",
    "require_service_account_scopes",
]
