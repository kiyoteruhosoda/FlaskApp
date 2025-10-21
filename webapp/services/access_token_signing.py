"""Helpers to resolve keys for access token signing and verification."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from flask import current_app
from jwt import algorithms as jwt_algorithms

from features.certs.application.services import default_certificate_services
from features.certs.application.use_cases import GetIssuedCertificateUseCase
from features.certs.domain.exceptions import (
    CertificateNotFoundError,
    CertificatePrivateKeyNotFoundError,
)
from features.certs.domain.usage import UsageType
from webapp.services.system_setting_service import (
    AccessTokenSigningSetting,
    AccessTokenSigningValidationError,
    SystemSettingService,
)
from core.settings import settings


_ALLOWED_RSA_ALGORITHMS = {"RS256", "RS384", "RS512"}
_ALLOWED_EC_ALGORITHMS = {"ES256", "ES384", "ES512"}
_ALLOWED_SERVER_ALGORITHMS = _ALLOWED_RSA_ALGORITHMS | _ALLOWED_EC_ALGORITHMS


class AccessTokenSigningError(RuntimeError):
    """Raised when signing configuration prevents issuing a token."""


class AccessTokenVerificationError(RuntimeError):
    """Raised when a token cannot be verified because key resolution failed."""


@dataclass(slots=True)
class SigningMaterial:
    """Resolved information for producing a signed JWT."""

    algorithm: str
    key: str | bytes
    headers: dict[str, str] | None
    kid: str | None
    setting: AccessTokenSigningSetting


def resolve_signing_material() -> SigningMaterial:
    """Return the key, algorithm, and headers for issuing an access token."""

    try:
        setting = SystemSettingService.get_access_token_signing_setting()
    except AccessTokenSigningValidationError as exc:
        raise AccessTokenSigningError(str(exc)) from exc
    if setting.is_builtin:
        secret = settings.get("JWT_SECRET_KEY")
        if not secret:
            raise AccessTokenSigningError("JWT secret key is not configured.")
        return SigningMaterial(
            algorithm="HS256",
            key=secret,
            headers=None,
            kid=None,
            setting=setting,
        )

    try:
        certificate = SystemSettingService.resolve_active_server_signing_certificate(setting)
    except AccessTokenSigningValidationError as exc:
        raise AccessTokenSigningError(str(exc)) from exc
    try:
        key_record = default_certificate_services.private_key_store.get(certificate.kid)
    except CertificatePrivateKeyNotFoundError as exc:
        raise AccessTokenSigningError("Private key for configured certificate is not available.") from exc

    algorithm = str(certificate.jwk.get("alg") or "").strip()
    if algorithm not in _ALLOWED_SERVER_ALGORITHMS:
        raise AccessTokenSigningError(f"Unsupported server signing algorithm: {algorithm or 'unknown'}")

    headers = {"kid": certificate.kid}
    return SigningMaterial(
        algorithm=algorithm,
        key=key_record.private_key_pem,
        headers=headers,
        kid=certificate.kid,
        setting=setting,
    )


def resolve_verification_key(algorithm: str, kid: str | None):
    """Resolve the key required to verify an access token."""

    if algorithm == "HS256":
        secret = settings.get("JWT_SECRET_KEY")
        if not secret:
            raise AccessTokenVerificationError("JWT secret key is not configured.")
        return secret

    normalized_alg = (algorithm or "").strip()
    if normalized_alg not in _ALLOWED_SERVER_ALGORITHMS:
        raise AccessTokenVerificationError(f"Unsupported JWT algorithm: {normalized_alg or 'unknown'}")

    if not kid:
        raise AccessTokenVerificationError("Missing key identifier for server signed token.")

    certificate = _load_active_server_signing_certificate(kid)
    jwk_payload = json.dumps(certificate.jwk)

    if normalized_alg in _ALLOWED_RSA_ALGORITHMS:
        return jwt_algorithms.RSAAlgorithm.from_jwk(jwk_payload)
    if normalized_alg in _ALLOWED_EC_ALGORITHMS:
        return jwt_algorithms.ECAlgorithm.from_jwk(jwk_payload)

    raise AccessTokenVerificationError(f"Unsupported JWT algorithm: {normalized_alg}")


def _load_active_server_signing_certificate(kid: str):
    try:
        certificate = GetIssuedCertificateUseCase().execute(kid)
    except CertificateNotFoundError as exc:
        raise AccessTokenSigningError("Configured certificate does not exist.") from exc

    if certificate.usage_type != UsageType.SERVER_SIGNING:
        raise AccessTokenSigningError("Configured certificate is not marked for server signing usage.")

    now = datetime.now(timezone.utc)
    revoked_at = _to_utc(certificate.revoked_at)
    if revoked_at is not None and revoked_at <= now:
        raise AccessTokenSigningError("Configured certificate has been revoked.")
    expires_at = _to_utc(certificate.expires_at)
    if expires_at is not None and expires_at <= now:
        raise AccessTokenSigningError("Configured certificate is expired.")
    if certificate.group is None:
        raise AccessTokenSigningError("Configured certificate is not assigned to a group.")

    return certificate


def _to_utc(value):
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "AccessTokenSigningError",
    "AccessTokenVerificationError",
    "SigningMaterial",
    "resolve_signing_material",
    "resolve_verification_key",
]
