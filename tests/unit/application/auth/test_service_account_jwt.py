from datetime import datetime, timedelta, timezone

import json
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from core.db import db
from bounded_contexts.certs.domain.usage import UsageType
from bounded_contexts.certs.infrastructure.models import CertificateGroupEntity
from webapp.auth.service_account_auth import (
    ServiceAccountJWTError,
    ServiceAccountTokenValidator,
)
from webapp.services.service_account_service import (
    ServiceAccountService,
    ServiceAccountValidationError,
)


class _InMemoryRedis:
    def __init__(self):
        self._store: dict[str, tuple[str, float]] = {}

    def _purge(self) -> None:
        now = time.monotonic()
        expired = [key for key, (_, exp) in self._store.items() if exp <= now]
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
def redis_store(app_context, monkeypatch):
    store = _InMemoryRedis()
    app_context.config["REDIS_URL"] = "redis://localhost:6379/0"
    monkeypatch.setattr(
        "webapp.auth.service_account_auth.redis.from_url",
        lambda url: store,
    )
    return store


def _generate_es256_key_pair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def _generate_rs256_key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def _build_jwk(public_pem: str, algorithm: str, kid: str) -> dict:
    public_key = load_pem_public_key(public_pem.encode("utf-8"))
    if algorithm == "ES256":
        jwk_json = ECAlgorithm.to_jwk(public_key)
    elif algorithm == "RS256":
        jwk_json = RSAAlgorithm.to_jwk(public_key)
    else:  # pragma: no cover - defensive branch
        raise ValueError(f"Unsupported algorithm: {algorithm}")

    jwk = json.loads(jwk_json)
    jwk["kid"] = kid
    jwk.setdefault("alg", algorithm)
    jwk.setdefault("use", "sig")
    return jwk


def _mock_jwks(monkeypatch, mapping: dict[str, list[dict]]):
    def fake_execute(self, group_code: str, *, latest_only: bool = False):
        if group_code not in mapping:
            raise AssertionError(f"unexpected group {group_code}")
        keys = mapping[group_code]
        if latest_only:
            keys = keys[:1]
        return {"keys": keys}

    monkeypatch.setattr(
        "webapp.auth.service_account_auth.ListJwksUseCase.execute", fake_execute
    )


def _create_certificate_group(
    group_code: str, *, usage: UsageType = UsageType.CLIENT_SIGNING
) -> str:
    entity = CertificateGroupEntity(
        group_code=group_code,
        display_name=group_code,
        auto_rotate=False,
        rotation_threshold_days=30,
        key_type="EC",
        key_curve="P-256",
        key_size=None,
        subject={"CN": group_code},
        usage_type=usage.value,
    )
    db.session.add(entity)
    db.session.commit()
    return entity.group_code


def _create_account(app, name: str, group_code: str, scopes: str):
    allowed = [scope.strip() for scope in scopes.split(",") if scope.strip()]
    return ServiceAccountService.create_account(
        name=name,
        description="",
        certificate_group_code=group_code,
        scope_names=scopes,
        active=True,
        allowed_scopes=allowed,
    )


def _issue_token(
    private_pem: bytes,
    *,
    name: str,
    audience: str,
    scopes: str,
    lifetime_minutes: int = 5,
    algorithm: str = "ES256",
    kid: str = "test-key",
    jti: str | None = None,
):
    now = datetime.now(timezone.utc)
    token_jti = jti or str(uuid.uuid4())
    payload = {
        "iss": name,
        "sub": name,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=lifetime_minutes)).timestamp()),
        "scope": scopes,
        "jti": token_jti,
    }
    headers = {"kid": kid}
    return jwt.encode(payload, private_pem, algorithm=algorithm, headers=headers)


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_success_es256(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    group_code = _create_certificate_group("maintenance-group")
    kid = "maintenance-key"
    _mock_jwks(monkeypatch, {group_code: [_build_jwk(public_pem, "ES256", kid)]})
    _create_account(
        app_context,
        "maintenance-bot",
        group_code,
        "maintenance:read,maintenance:write",
    )

    token = _issue_token(
        private_pem,
        name="maintenance-bot",
        audience="nolumia:maintenance",
        scopes="maintenance:read maintenance:write",
        kid=kid,
    )

    account, claims = ServiceAccountTokenValidator.verify(
        token,
        audience="nolumia:maintenance",
        required_scopes=["maintenance:read"],
    )

    assert account.name == "maintenance-bot"
    assert claims["aud"] == "nolumia:maintenance"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_invalid_scope(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    group_code = _create_certificate_group("scope-group")
    kid = "scope-key"
    _mock_jwks(monkeypatch, {group_code: [_build_jwk(public_pem, "ES256", kid)]})
    _create_account(app_context, "scope-bot", group_code, "maintenance:read")
    token = _issue_token(
        private_pem,
        name="scope-bot",
        audience="nolumia:maintenance",
        scopes="maintenance:read",
        kid=kid,
    )

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(token, audience="nolumia:maintenance", required_scopes=["maintenance:write"])

    assert exc.value.code == "InvalidScope"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_unknown_kid(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    group_code = _create_certificate_group("unknown-group")
    _mock_jwks(
        monkeypatch,
        {group_code: [_build_jwk(public_pem, "ES256", "other-key")]},
    )
    _create_account(app_context, "unknown-kid", group_code, "maintenance:read")
    token = _issue_token(
        private_pem,
        name="unknown-kid",
        audience="nolumia:maintenance",
        scopes="maintenance:read",
        kid="missing-key",
    )

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(
            token,
            audience="nolumia:maintenance",
            required_scopes=["maintenance:read"],
        )

    assert exc.value.code == "InvalidSignature"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_expired(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    group_code = _create_certificate_group("expired-group")
    kid = "expired-key"
    _mock_jwks(monkeypatch, {group_code: [_build_jwk(public_pem, "ES256", kid)]})
    _create_account(app_context, "expired-bot", group_code, "maintenance:read")
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "expired-bot",
        "sub": "expired-bot",
        "aud": "nolumia:maintenance",
        "iat": int((now - timedelta(minutes=20)).timestamp()),
        "exp": int((now - timedelta(minutes=10)).timestamp()),
        "scope": "maintenance:read",
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, private_pem, algorithm="ES256", headers={"kid": kid})

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(token, audience="nolumia:maintenance", required_scopes=["maintenance:read"])

    assert exc.value.code == "ExpiredToken"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_unknown_account(app_context):
    private_pem, public_pem = _generate_es256_key_pair()
    # アカウント未登録
    token = _issue_token(private_pem, name="ghost-bot", audience="nolumia:maintenance", scopes="maintenance:read")

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(token, audience="nolumia:maintenance", required_scopes=["maintenance:read"])

    assert exc.value.code == "UnknownAccount"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_disabled_account(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    group_code = _create_certificate_group("disabled-group")
    kid = "disabled-key"
    _mock_jwks(monkeypatch, {group_code: [_build_jwk(public_pem, "ES256", kid)]})
    account = _create_account(app_context, "disabled-bot", group_code, "maintenance:read")
    account.active_flg = False
    db.session.commit()

    token = _issue_token(
        private_pem,
        name="disabled-bot",
        audience="nolumia:maintenance",
        scopes="maintenance:read",
        kid=kid,
    )

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(token, audience="nolumia:maintenance", required_scopes=["maintenance:read"])

    assert exc.value.code == "DisabledAccount"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_lifetime_limit(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    group_code = _create_certificate_group("long-group")
    kid = "long-key"
    _mock_jwks(monkeypatch, {group_code: [_build_jwk(public_pem, "ES256", kid)]})
    _create_account(app_context, "long-bot", group_code, "maintenance:read")
    token = _issue_token(
        private_pem,
        name="long-bot",
        audience="nolumia:maintenance",
        scopes="maintenance:read",
        lifetime_minutes=15,
        kid=kid,
    )

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(token, audience="nolumia:maintenance", required_scopes=["maintenance:read"])

    assert exc.value.code == "ExpiredToken"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_success_rs256(app_context, monkeypatch):
    private_pem, public_pem = _generate_rs256_key_pair()
    group_code = _create_certificate_group("rsa-group")
    kid = "rsa-key"
    _mock_jwks(monkeypatch, {group_code: [_build_jwk(public_pem, "RS256", kid)]})
    _create_account(app_context, "rsa-bot", group_code, "maintenance:read")
    token = _issue_token(
        private_pem,
        name="rsa-bot",
        audience="nolumia:maintenance",
        scopes="maintenance:read",
        algorithm="RS256",
        kid=kid,
    )

    account, _ = ServiceAccountTokenValidator.verify(
        token,
        audience="nolumia:maintenance",
        required_scopes=["maintenance:read"],
    )

    assert account.name == "rsa-bot"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_missing_jti(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    group_code = _create_certificate_group("missing-jti-group")
    kid = "missing-jti"
    _mock_jwks(monkeypatch, {group_code: [_build_jwk(public_pem, "ES256", kid)]})
    _create_account(app_context, "missing-jti", group_code, "maintenance:read")

    now = datetime.now(timezone.utc)
    payload = {
        "iss": "missing-jti",
        "sub": "missing-jti",
        "aud": "nolumia:maintenance",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "scope": "maintenance:read",
    }
    token = jwt.encode(payload, private_pem, algorithm="ES256", headers={"kid": kid})

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(
            token,
            audience="nolumia:maintenance",
            required_scopes=["maintenance:read"],
        )

    assert exc.value.code == "MissingJTI"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_invalid_jti(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    group_code = _create_certificate_group("invalid-jti-group")
    kid = "invalid-jti"
    _mock_jwks(monkeypatch, {group_code: [_build_jwk(public_pem, "ES256", kid)]})
    _create_account(app_context, "invalid-jti", group_code, "maintenance:read")

    now = datetime.now(timezone.utc)
    payload = {
        "iss": "invalid-jti",
        "sub": "invalid-jti",
        "aud": "nolumia:maintenance",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "scope": "maintenance:read",
        "jti": "not-a-uuid",
    }
    token = jwt.encode(payload, private_pem, algorithm="ES256", headers={"kid": kid})

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(
            token,
            audience="nolumia:maintenance",
            required_scopes=["maintenance:read"],
        )

    assert exc.value.code == "InvalidJTI"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_replay_detected(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    group_code = _create_certificate_group("replay-group")
    kid = "replay-key"
    _mock_jwks(monkeypatch, {group_code: [_build_jwk(public_pem, "ES256", kid)]})
    _create_account(app_context, "replay-bot", group_code, "maintenance:read")

    token = _issue_token(
        private_pem,
        name="replay-bot",
        audience="nolumia:maintenance",
        scopes="maintenance:read",
        kid=kid,
        jti=str(uuid.uuid4()),
    )

    ServiceAccountTokenValidator.verify(
        token,
        audience="nolumia:maintenance",
        required_scopes=["maintenance:read"],
    )

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(
            token,
            audience="nolumia:maintenance",
            required_scopes=["maintenance:read"],
        )

    assert exc.value.code == "ReplayDetected"


@pytest.mark.usefixtures("app_context")
def test_service_account_certificate_group_validation(app_context):
    group_code = _create_certificate_group("normalize-group")

    account = ServiceAccountService.create_account(
        name="normalize-bot",
        description=None,
        certificate_group_code=f"  {group_code}  ",
        scope_names="maintenance:read",
        active=True,
        allowed_scopes=["maintenance:read"],
    )

    assert account.certificate_group_code == group_code

    with pytest.raises(ServiceAccountValidationError) as exc:
        ServiceAccountService.create_account(
            name="invalid-bot",
            description=None,
            certificate_group_code="missing-group",
            scope_names="maintenance:read",
            active=True,
            allowed_scopes=["maintenance:read"],
        )

    assert exc.value.field == "certificate_group_code"

    wrong_usage_group = _create_certificate_group(
        "server-group", usage=UsageType.SERVER_SIGNING
    )

    with pytest.raises(ServiceAccountValidationError) as exc_wrong_usage:
        ServiceAccountService.create_account(
            name="wrong-usage",
            description=None,
            certificate_group_code=wrong_usage_group,
            scope_names="maintenance:read",
            active=True,
            allowed_scopes=["maintenance:read"],
        )

    assert exc_wrong_usage.value.field == "certificate_group_code"
