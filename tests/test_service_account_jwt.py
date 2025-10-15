from datetime import datetime, timedelta, timezone

import json
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

from core.db import db
from webapp.auth.service_account_auth import (
    ServiceAccountJWTError,
    ServiceAccountTokenValidator,
)
from webapp.services.service_account_service import (
    ServiceAccountService,
    ServiceAccountValidationError,
)


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
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_get(url, *args, **kwargs):
        if url not in mapping:
            raise AssertionError(f"unexpected url {url}")
        return FakeResponse({"keys": mapping[url]})

    monkeypatch.setattr("requests.get", fake_get)


def _create_account(app, name: str, jtk_endpoint: str, scopes: str):
    allowed = [scope.strip() for scope in scopes.split(",") if scope.strip()]
    return ServiceAccountService.create_account(
        name=name,
        description="",
        jtk_endpoint=jtk_endpoint,
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
):
    now = datetime.now(timezone.utc)
    payload = {
        "iss": name,
        "sub": name,
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=lifetime_minutes)).timestamp()),
        "scope": scopes,
    }
    headers = {"kid": kid}
    return jwt.encode(payload, private_pem, algorithm=algorithm, headers=headers)


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_success_es256(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    endpoint = "https://example.com/jwks/maintenance"
    kid = "maintenance-key"
    _mock_jwks(monkeypatch, {endpoint: [_build_jwk(public_pem, "ES256", kid)]})
    _create_account(app_context, "maintenance-bot", endpoint, "maintenance:read,maintenance:write")

    token = _issue_token(
        private_pem,
        name="maintenance-bot",
        audience="familink:maintenance",
        scopes="maintenance:read maintenance:write",
        kid=kid,
    )

    account, claims = ServiceAccountTokenValidator.verify(
        token,
        audience="familink:maintenance",
        required_scopes=["maintenance:read"],
    )

    assert account.name == "maintenance-bot"
    assert claims["aud"] == "familink:maintenance"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_invalid_scope(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    endpoint = "https://example.com/jwks/scope"
    kid = "scope-key"
    _mock_jwks(monkeypatch, {endpoint: [_build_jwk(public_pem, "ES256", kid)]})
    _create_account(app_context, "scope-bot", endpoint, "maintenance:read")
    token = _issue_token(
        private_pem,
        name="scope-bot",
        audience="familink:maintenance",
        scopes="maintenance:read",
        kid=kid,
    )

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(token, audience="familink:maintenance", required_scopes=["maintenance:write"])

    assert exc.value.code == "InvalidScope"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_unknown_kid(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    endpoint = "https://example.com/jwks/unknown"
    _mock_jwks(monkeypatch, {endpoint: [_build_jwk(public_pem, "ES256", "other-key")]})
    _create_account(app_context, "unknown-kid", endpoint, "maintenance:read")
    token = _issue_token(
        private_pem,
        name="unknown-kid",
        audience="familink:maintenance",
        scopes="maintenance:read",
        kid="missing-key",
    )

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(
            token,
            audience="familink:maintenance",
            required_scopes=["maintenance:read"],
        )

    assert exc.value.code == "InvalidSignature"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_expired(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    endpoint = "https://example.com/jwks/expired"
    kid = "expired-key"
    _mock_jwks(monkeypatch, {endpoint: [_build_jwk(public_pem, "ES256", kid)]})
    _create_account(app_context, "expired-bot", endpoint, "maintenance:read")
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "expired-bot",
        "sub": "expired-bot",
        "aud": "familink:maintenance",
        "iat": int((now - timedelta(minutes=20)).timestamp()),
        "exp": int((now - timedelta(minutes=10)).timestamp()),
        "scope": "maintenance:read",
    }
    token = jwt.encode(payload, private_pem, algorithm="ES256", headers={"kid": kid})

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(token, audience="familink:maintenance", required_scopes=["maintenance:read"])

    assert exc.value.code == "ExpiredToken"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_unknown_account(app_context):
    private_pem, public_pem = _generate_es256_key_pair()
    # アカウント未登録
    token = _issue_token(private_pem, name="ghost-bot", audience="familink:maintenance", scopes="maintenance:read")

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(token, audience="familink:maintenance", required_scopes=["maintenance:read"])

    assert exc.value.code == "UnknownAccount"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_disabled_account(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    endpoint = "https://example.com/jwks/disabled"
    kid = "disabled-key"
    _mock_jwks(monkeypatch, {endpoint: [_build_jwk(public_pem, "ES256", kid)]})
    account = _create_account(app_context, "disabled-bot", endpoint, "maintenance:read")
    account.active_flg = False
    db.session.commit()

    token = _issue_token(
        private_pem,
        name="disabled-bot",
        audience="familink:maintenance",
        scopes="maintenance:read",
        kid=kid,
    )

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(token, audience="familink:maintenance", required_scopes=["maintenance:read"])

    assert exc.value.code == "DisabledAccount"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_lifetime_limit(app_context, monkeypatch):
    private_pem, public_pem = _generate_es256_key_pair()
    endpoint = "https://example.com/jwks/long"
    kid = "long-key"
    _mock_jwks(monkeypatch, {endpoint: [_build_jwk(public_pem, "ES256", kid)]})
    _create_account(app_context, "long-bot", endpoint, "maintenance:read")
    token = _issue_token(
        private_pem,
        name="long-bot",
        audience="familink:maintenance",
        scopes="maintenance:read",
        lifetime_minutes=15,
        kid=kid,
    )

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(token, audience="familink:maintenance", required_scopes=["maintenance:read"])

    assert exc.value.code == "ExpiredToken"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_success_rs256(app_context, monkeypatch):
    private_pem, public_pem = _generate_rs256_key_pair()
    endpoint = "https://example.com/jwks/rsa"
    kid = "rsa-key"
    _mock_jwks(monkeypatch, {endpoint: [_build_jwk(public_pem, "RS256", kid)]})
    _create_account(app_context, "rsa-bot", endpoint, "maintenance:read")
    token = _issue_token(
        private_pem,
        name="rsa-bot",
        audience="familink:maintenance",
        scopes="maintenance:read",
        algorithm="RS256",
        kid=kid,
    )

    account, _ = ServiceAccountTokenValidator.verify(
        token,
        audience="familink:maintenance",
        required_scopes=["maintenance:read"],
    )

    assert account.name == "rsa-bot"


@pytest.mark.usefixtures("app_context")
def test_service_account_jtk_endpoint_validation(app_context):
    account = ServiceAccountService.create_account(
        name="normalize-bot",
        description=None,
        jtk_endpoint=" https://keys.example.com/jwks ",
        scope_names="maintenance:read",
        active=True,
        allowed_scopes=["maintenance:read"],
    )

    assert account.jtk_endpoint == "https://keys.example.com/jwks"

    with pytest.raises(ServiceAccountValidationError) as exc:
        ServiceAccountService.create_account(
            name="invalid-bot",
            description=None,
            jtk_endpoint="ftp://keys.example.com/jwks",
            scope_names="maintenance:read",
            active=True,
            allowed_scopes=["maintenance:read"],
        )

    assert exc.value.field == "jtk_endpoint"
