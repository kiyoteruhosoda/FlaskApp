from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from core.db import db
from webapp.auth.service_account_auth import (
    ServiceAccountJWTError,
    ServiceAccountTokenValidator,
)
from webapp.services.service_account_service import ServiceAccountService


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


def _create_account(app, name: str, public_key: str, scopes: str):
    allowed = [scope.strip() for scope in scopes.split(",") if scope.strip()]
    return ServiceAccountService.create_account(
        name=name,
        description="",
        public_key=public_key,
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
    return jwt.encode(payload, private_pem, algorithm=algorithm)


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_success_es256(app_context):
    private_pem, public_pem = _generate_es256_key_pair()
    _create_account(app_context, "maintenance-bot", public_pem, "maintenance:read,maintenance:write")

    token = _issue_token(private_pem, name="maintenance-bot", audience="familink:maintenance", scopes="maintenance:read maintenance:write")

    account, claims = ServiceAccountTokenValidator.verify(
        token,
        audience="familink:maintenance",
        required_scopes=["maintenance:read"],
    )

    assert account.name == "maintenance-bot"
    assert claims["aud"] == "familink:maintenance"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_invalid_scope(app_context):
    private_pem, public_pem = _generate_es256_key_pair()
    _create_account(app_context, "scope-bot", public_pem, "maintenance:read")
    token = _issue_token(private_pem, name="scope-bot", audience="familink:maintenance", scopes="maintenance:read")

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(token, audience="familink:maintenance", required_scopes=["maintenance:write"])

    assert exc.value.code == "InvalidScope"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_expired(app_context):
    private_pem, public_pem = _generate_es256_key_pair()
    _create_account(app_context, "expired-bot", public_pem, "maintenance:read")
    now = datetime.now(timezone.utc)
    payload = {
        "iss": "expired-bot",
        "sub": "expired-bot",
        "aud": "familink:maintenance",
        "iat": int((now - timedelta(minutes=20)).timestamp()),
        "exp": int((now - timedelta(minutes=10)).timestamp()),
        "scope": "maintenance:read",
    }
    token = jwt.encode(payload, private_pem, algorithm="ES256")

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
def test_service_account_jwt_disabled_account(app_context):
    private_pem, public_pem = _generate_es256_key_pair()
    account = _create_account(app_context, "disabled-bot", public_pem, "maintenance:read")
    account.active_flg = False
    db.session.commit()

    token = _issue_token(private_pem, name="disabled-bot", audience="familink:maintenance", scopes="maintenance:read")

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(token, audience="familink:maintenance", required_scopes=["maintenance:read"])

    assert exc.value.code == "DisabledAccount"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_lifetime_limit(app_context):
    private_pem, public_pem = _generate_es256_key_pair()
    _create_account(app_context, "long-bot", public_pem, "maintenance:read")
    token = _issue_token(private_pem, name="long-bot", audience="familink:maintenance", scopes="maintenance:read", lifetime_minutes=15)

    with pytest.raises(ServiceAccountJWTError) as exc:
        ServiceAccountTokenValidator.verify(token, audience="familink:maintenance", required_scopes=["maintenance:read"])

    assert exc.value.code == "ExpiredToken"


@pytest.mark.usefixtures("app_context")
def test_service_account_jwt_success_rs256(app_context):
    private_pem, public_pem = _generate_rs256_key_pair()
    _create_account(app_context, "rsa-bot", public_pem, "maintenance:read")
    token = _issue_token(
        private_pem,
        name="rsa-bot",
        audience="familink:maintenance",
        scopes="maintenance:read",
        algorithm="RS256",
    )

    account, _ = ServiceAccountTokenValidator.verify(
        token,
        audience="familink:maintenance",
        required_scopes=["maintenance:read"],
    )

    assert account.name == "rsa-bot"


@pytest.mark.usefixtures("app_context")
def test_service_account_public_key_normalization(app_context):
    private_pem, public_pem = _generate_es256_key_pair()
    pem_body = "".join(public_pem.splitlines()[1:-1])  # PEMヘッダ・フッタを除外
    account = ServiceAccountService.create_account(
        name="normalize-bot",
        description=None,
        public_key=pem_body,
        scope_names="maintenance:read",
        active=True,
        allowed_scopes=["maintenance:read"],
    )

    assert "BEGIN PUBLIC KEY" in account.public_key
    assert account.public_key.strip().startswith("-----BEGIN PUBLIC KEY-----")
    assert account.public_key.strip().endswith("-----END PUBLIC KEY-----")
