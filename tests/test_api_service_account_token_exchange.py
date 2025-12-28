from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from core.db import db
from features.certs.application.use_cases import IssueCertificateForGroupUseCase
from features.certs.domain.usage import UsageType
from features.certs.infrastructure.models import CertificateGroupEntity
from webapp.services.service_account_service import ServiceAccountService
from webapp.services.token_service import TokenService
from shared.application.authenticated_principal import AuthenticatedPrincipal


JWT_BEARER_GRANT = "urn:ietf:params:oauth:grant-type:jwt-bearer"


class _InMemoryRedis:
    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float]] = {}

    def _purge(self) -> None:
        now = time.monotonic()
        expired = [key for key, (_, expiry) in self._store.items() if expiry <= now]
        for key in expired:
            del self._store[key]

    def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        self._purge()
        exists = key in self._store
        if nx and exists:
            return False
        if xx and not exists:
            return False

        ttl_seconds: float | None = None
        if ex is not None:
            ttl_seconds = float(ex)
        elif px is not None:
            ttl_seconds = float(px) / 1000.0

        expiry = (
            time.monotonic() + ttl_seconds if ttl_seconds is not None else float("inf")
        )
        self._store[key] = (value, expiry)
        return True


@pytest.fixture(autouse=True)
def _redis_store(app_context, monkeypatch):
    store = _InMemoryRedis()
    app_context.config["REDIS_URL"] = "redis://localhost:6379/0"
    monkeypatch.setattr(
        "webapp.auth.service_account_auth.redis.from_url",
        lambda url: store,
    )
    return store


def _prepare_service_account(app_context, *, scopes: list[str]):
    group_code = f"svc-{uuid.uuid4().hex[:8]}"
    group = CertificateGroupEntity(
        group_code=group_code,
        display_name=group_code,
        auto_rotate=False,
        rotation_threshold_days=30,
        key_type="EC",
        key_curve="P-256",
        key_size=None,
        subject={"CN": group_code},
        usage_type=UsageType.CLIENT_SIGNING.value,
    )
    db.session.add(group)
    db.session.commit()

    issued = IssueCertificateForGroupUseCase().execute(group_code)

    account = ServiceAccountService.create_account(
        name=f"{group_code}-bot",
        description="",
        certificate_group_code=group_code,
        scope_names=scopes,
        active=True,
        allowed_scopes=scopes,
    )

    return account, issued


def _build_assertion(
    private_key_pem: str,
    *,
    account_name: str,
    audience: str,
    scope: str,
    kid: str,
    jti: str | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": account_name,
        "sub": account_name,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "jti": jti or uuid.uuid4().hex,
        "scope": scope,
    }
    headers = {"alg": "ES256", "kid": kid, "typ": "JWT"}
    return jwt.encode(payload, private_key_pem, algorithm="ES256", headers=headers)


def test_service_account_token_exchange_success(app_context):
    audience = "https://example.com/api/token"
    app_context.config["SERVICE_ACCOUNT_SIGNING_AUDIENCE"] = audience
    client = app_context.test_client()
    account, issued = _prepare_service_account(app_context, scopes=["maintenance:read", "certificate:sign"])

    assertion = _build_assertion(
        issued.private_key_pem,
        account_name=account.name,
        audience=audience,
        scope="maintenance:read certificate:sign",
        kid=issued.kid,
    )

    response = client.post(
        "/api/token",
        json={"grant_type": JWT_BEARER_GRANT, "assertion": assertion},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["token_type"] == "Bearer"
    expected_scope = TokenService._normalize_scope(["maintenance:read", "certificate:sign"])[1]
    assert payload["scope"] == expected_scope
    assert payload["expires_in"] == TokenService.ACCESS_TOKEN_EXPIRE_SECONDS

    decoded = jwt.decode(
        payload["access_token"],
        options={"verify_signature": False, "verify_aud": False},
    )
    assert decoded["subject_type"] == "system"
    assert decoded["sub"] == f"s+{account.service_account_id}"
    assert "service_account" not in decoded
    assert "service_account_id" not in decoded
    assert decoded["scope"] == expected_scope

    with app_context.app_context():
        principal = TokenService.verify_access_token(payload["access_token"])
        assert isinstance(principal, AuthenticatedPrincipal)
        assert principal.subject_type == "system"
        assert principal.id == account.service_account_id
        assert principal.scope == frozenset(expected_scope.split())
        assert principal.display_name == f"{account.name} (sa)"


def test_service_account_token_exchange_missing_scope(app_context):
    audience = "https://example.com/api/token"
    app_context.config["SERVICE_ACCOUNT_SIGNING_AUDIENCE"] = audience
    client = app_context.test_client()
    account, issued = _prepare_service_account(app_context, scopes=["maintenance:read"])

    now = datetime.now(timezone.utc)
    payload = {
        "iss": account.name,
        "sub": account.name,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    assertion = jwt.encode(
        payload,
        issued.private_key_pem,
        algorithm="ES256",
        headers={"alg": "ES256", "kid": issued.kid, "typ": "JWT"},
    )

    response = client.post(
        "/api/token",
        json={"grant_type": JWT_BEARER_GRANT, "assertion": assertion},
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "invalid_grant"


def test_service_account_token_exchange_rejects_disallowed_scope(app_context):
    audience = "https://example.com/api/token"
    app_context.config["SERVICE_ACCOUNT_SIGNING_AUDIENCE"] = audience
    client = app_context.test_client()
    account, issued = _prepare_service_account(app_context, scopes=["maintenance:read"])

    assertion = _build_assertion(
        issued.private_key_pem,
        account_name=account.name,
        audience=audience,
        scope="maintenance:read certificate:sign",
        kid=issued.kid,
    )

    response = client.post(
        "/api/token",
        json={"grant_type": JWT_BEARER_GRANT, "assertion": assertion},
    )

    assert response.status_code == 403
    body = response.get_json()
    assert body["error"] == "invalid_grant"


def test_service_account_token_exchange_rejects_replay(app_context):
    audience = "https://example.com/api/token"
    app_context.config["SERVICE_ACCOUNT_SIGNING_AUDIENCE"] = audience
    client = app_context.test_client()
    account, issued = _prepare_service_account(app_context, scopes=["maintenance:read"])

    jti = uuid.uuid4().hex
    assertion = _build_assertion(
        issued.private_key_pem,
        account_name=account.name,
        audience=audience,
        scope="maintenance:read",
        kid=issued.kid,
        jti=jti,
    )

    first = client.post(
        "/api/token",
        json={"grant_type": JWT_BEARER_GRANT, "assertion": assertion},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/token",
        json={"grant_type": JWT_BEARER_GRANT, "assertion": assertion},
    )

    assert second.status_code == 403
    body = second.get_json()
    assert body["error"] == "invalid_grant"


def test_service_account_token_exchange_invalid_grant_type(app_context):
    audience = "https://example.com/api/token"
    app_context.config["SERVICE_ACCOUNT_SIGNING_AUDIENCE"] = audience
    client = app_context.test_client()
    account, issued = _prepare_service_account(app_context, scopes=["maintenance:read"])

    assertion = _build_assertion(
        issued.private_key_pem,
        account_name=account.name,
        audience=audience,
        scope="maintenance:read",
        kid=issued.kid,
    )

    response = client.post(
        "/api/token",
        json={"grant_type": "client_credentials", "assertion": assertion},
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "unsupported_grant_type"
