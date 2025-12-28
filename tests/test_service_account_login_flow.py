from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from core.db import db
from features.certs.application.use_cases import (
    IssueCertificateForGroupUseCase,
    ListJwksUseCase,
)
from features.certs.domain.usage import UsageType
from features.certs.infrastructure.models import CertificateGroupEntity
from webapp.services.service_account_api_key_service import ServiceAccountApiKeyService
from webapp.services.service_account_service import ServiceAccountService


def _prepare_service_account_signing_context(app_context, *, group_code: str):
    group = CertificateGroupEntity(
        group_code=group_code,
        display_name=f"{group_code.title()}",
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

    issued = IssueCertificateForGroupUseCase().execute(group.group_code)

    account = ServiceAccountService.create_account(
        name=f"{group_code}-bot",
        description="",
        certificate_group_code=group.group_code,
        scope_names=["maintenance:read", "certificate:sign"],
        active=True,
        allowed_scopes=["maintenance:read", "certificate:sign"],
    )

    _, api_key_value = ServiceAccountApiKeyService.create_key(
        account.service_account_id,
        scopes="certificate:sign",
        expires_at=None,
        created_by="admin@example.com",
    )

    return app_context.test_client(), account, issued, api_key_value


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@pytest.mark.usefixtures("app_context")
def test_service_account_end_to_end_login_flow(app_context, monkeypatch):
    client, account, issued, api_key_value = _prepare_service_account_signing_context(
        app_context, group_code="client-signing"
    )

    jwks_payload = ListJwksUseCase().execute(account.certificate_group_code)
    assert any(key.get("kid") == issued.kid for key in jwks_payload.get("keys", []))

    now = datetime.now(timezone.utc)
    audience = "http://localhost/api/maintenance"
    monkeypatch.setenv("SERVICE_ACCOUNT_SIGNING_AUDIENCE", audience)
    header_segment = _b64url(
        json.dumps({"alg": "ES256", "kid": issued.kid, "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
    )
    payload_segment = _b64url(
        json.dumps(
            {
                "iss": account.name,
                "sub": account.name,
                "aud": audience,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
                "scope": "maintenance:read certificate:sign",
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signing_input_encoded = base64.b64encode(signing_input).decode("ascii")

    sign_response = client.post(
        "/api/service_accounts/signatures",
        json={
            "signingInput": signing_input_encoded,
            "signingInputEncoding": "base64",
            "kid": issued.kid,
        },
        headers={"Authorization": f"ApiKey {api_key_value}"},
    )
    assert sign_response.status_code == 200
    signature_payload = sign_response.get_json()
    signature_segment = signature_payload["signature"]
    assert signature_payload["kid"] == issued.kid

    token = f"{header_segment}.{payload_segment}.{signature_segment}"

    response = client.get(
        "/api/maintenance/ping",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["service_account"] == account.name


@pytest.mark.usefixtures("app_context")
def test_service_account_signature_accepts_plain_encoding(app_context, monkeypatch):
    client, account, issued, api_key_value = _prepare_service_account_signing_context(
        app_context, group_code="client-signing-plain"
    )

    now = datetime.now(timezone.utc)
    audience = "http://localhost/api/maintenance"
    monkeypatch.setenv("SERVICE_ACCOUNT_SIGNING_AUDIENCE", audience)
    header_segment = _b64url(
        json.dumps({"alg": "ES256", "kid": issued.kid, "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
    )
    payload_segment = _b64url(
        json.dumps(
            {
                "iss": account.name,
                "sub": account.name,
                "aud": audience,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
                "scope": "maintenance:read certificate:sign",
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signing_input_plain = f"{header_segment}.{payload_segment}"

    response = client.post(
        "/api/service_accounts/signatures",
        json={
            "signingInput": signing_input_plain,
            "signingInputEncoding": "plain",
            "kid": issued.kid,
        },
        headers={"Authorization": f"ApiKey {api_key_value}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["kid"] == issued.kid
    assert payload["signature"]


@pytest.mark.usefixtures("app_context")
def test_service_account_signature_accepts_plain_encoding_with_hash_hint(app_context, monkeypatch):
    client, account, issued, api_key_value = _prepare_service_account_signing_context(
        app_context, group_code="client-signing-plain-hash"
    )

    now = datetime.now(timezone.utc)
    audience = "https://nolumia.com/api/login/token"
    monkeypatch.setenv("SERVICE_ACCOUNT_SIGNING_AUDIENCE", audience)

    header_segment = _b64url(
        json.dumps({"alg": "ES256", "kid": issued.kid, "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
    )
    payload_segment = _b64url(
        json.dumps(
            {
                "iss": account.name,
                "sub": account.name,
                "aud": audience,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
                "jti": "8ae8ecf4604afcdf6cc10de12cdeec7c",
                "scope": "",
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signing_input_plain = f"{header_segment}.{payload_segment}"

    response = client.post(
        "/api/service_accounts/signatures",
        data=json.dumps(
            {
                "signingInput": signing_input_plain,
                "signingInputEncoding": "plain",
                "kid": issued.kid,
                "hashAlgorithm": "SHA256",
            }
        ),
        content_type="application/json",
        headers={"Authorization": f"ApiKey {api_key_value}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["kid"] == issued.kid
    assert payload["signature"]


@pytest.mark.usefixtures("app_context")
def test_service_account_signature_rejects_unexpected_audience(app_context, monkeypatch):
    client, account, issued, api_key_value = _prepare_service_account_signing_context(
        app_context, group_code="client-signing-2"
    )

    monkeypatch.setenv("SERVICE_ACCOUNT_SIGNING_AUDIENCE", "https://expected.example.com")

    now = datetime.now(timezone.utc)
    audience = "https://unapproved.example.com"
    header_segment = _b64url(
        json.dumps({"alg": "ES256", "kid": issued.kid, "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
    )
    payload_segment = _b64url(
        json.dumps(
            {
                "iss": account.name,
                "sub": account.name,
                "aud": audience,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
                "scope": "maintenance:read certificate:sign",
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signing_input_encoded = base64.b64encode(signing_input).decode("ascii")

    response = client.post(
        "/api/service_accounts/signatures",
        json={
            "signingInput": signing_input_encoded,
            "signingInputEncoding": "base64",
            "kid": issued.kid,
        },
        headers={"Authorization": f"ApiKey {api_key_value}"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "The signing request audience is not allowed."


@pytest.mark.usefixtures("app_context")
def test_service_account_signature_rejects_invalid_json_body(app_context):
    client, _account, _issued, api_key_value = _prepare_service_account_signing_context(
        app_context, group_code="client-signing-invalid-json"
    )

    response = client.post(
        "/api/service_accounts/signatures",
        data="not-json",
        content_type="application/json",
        headers={"Authorization": f"ApiKey {api_key_value}"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "Request body must be a valid JSON object."


@pytest.mark.usefixtures("app_context")
def test_service_account_signature_rejects_non_object_json_body(app_context):
    client, _account, _issued, api_key_value = _prepare_service_account_signing_context(
        app_context, group_code="client-signing-json-array"
    )

    response = client.post(
        "/api/service_accounts/signatures",
        data=json.dumps(["signingInput", "kid"]),
        content_type="application/json",
        headers={"Authorization": f"ApiKey {api_key_value}"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "Request body must be a JSON object."


@pytest.mark.usefixtures("app_context")
def test_service_account_signature_rejects_invalid_kid(app_context):
    client, account, _issued, api_key_value = _prepare_service_account_signing_context(
        app_context, group_code="client-signing-invalid-kid"
    )

    other_group = CertificateGroupEntity(
        group_code="server-signing-group",
        display_name="Server Signing",
        auto_rotate=False,
        rotation_threshold_days=30,
        key_type="EC",
        key_curve="P-256",
        key_size=None,
        subject={"CN": "server"},
        usage_type=UsageType.SERVER_SIGNING.value,
    )
    db.session.add(other_group)
    db.session.commit()

    other_certificate = IssueCertificateForGroupUseCase().execute(other_group.group_code)

    now = datetime.now(timezone.utc)
    header_segment = _b64url(
        json.dumps(
            {"alg": "ES256", "kid": other_certificate.kid, "typ": "JWT"},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    payload_segment = _b64url(
        json.dumps(
            {
                "iss": account.name,
                "sub": account.name,
                "aud": "https://example.com",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
                "scope": "maintenance:read certificate:sign",
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signing_input_encoded = base64.b64encode(signing_input).decode("ascii")

    response = client.post(
        "/api/service_accounts/signatures",
        json={
            "signingInput": signing_input_encoded,
            "signingInputEncoding": "base64",
            "kid": other_certificate.kid,
        },
        headers={"Authorization": f"ApiKey {api_key_value}"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "The signing request key is not permitted for this service account."


@pytest.mark.usefixtures("app_context")
def test_service_account_signature_requires_scope_claim(app_context):
    client, account, issued, api_key_value = _prepare_service_account_signing_context(
        app_context, group_code="client-signing-3"
    )

    now = datetime.now(timezone.utc)
    header_segment = _b64url(
        json.dumps({"alg": "ES256", "kid": issued.kid, "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
    )
    payload_segment = _b64url(
        json.dumps(
            {
                "iss": account.name,
                "sub": account.name,
                "aud": "https://example.com",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signing_input_encoded = base64.b64encode(signing_input).decode("ascii")

    response = client.post(
        "/api/service_accounts/signatures",
        json={
            "signingInput": signing_input_encoded,
            "signingInputEncoding": "base64",
            "kid": issued.kid,
        },
        headers={"Authorization": f"ApiKey {api_key_value}"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "The signing request must include a scope claim."


@pytest.mark.usefixtures("app_context")
def test_service_account_signature_allows_empty_scope(app_context):
    client, account, issued, api_key_value = _prepare_service_account_signing_context(
        app_context, group_code="client-signing-empty-scope"
    )

    now = datetime.now(timezone.utc)
    header_segment = _b64url(
        json.dumps({"alg": "ES256", "kid": issued.kid, "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
    )
    payload_segment = _b64url(
        json.dumps(
            {
                "iss": account.name,
                "sub": account.name,
                "aud": "https://example.com",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
                "scope": "",
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signing_input_encoded = base64.b64encode(signing_input).decode("ascii")

    response = client.post(
        "/api/service_accounts/signatures",
        json={
            "signingInput": signing_input_encoded,
            "signingInputEncoding": "base64",
            "kid": issued.kid,
        },
        headers={"Authorization": f"ApiKey {api_key_value}"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["kid"] == issued.kid


@pytest.mark.usefixtures("app_context")
def test_service_account_signature_rejects_unassigned_scope(app_context):
    client, account, issued, api_key_value = _prepare_service_account_signing_context(
        app_context, group_code="client-signing-4"
    )

    now = datetime.now(timezone.utc)
    header_segment = _b64url(
        json.dumps({"alg": "ES256", "kid": issued.kid, "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
    )
    payload_segment = _b64url(
        json.dumps(
            {
                "iss": account.name,
                "sub": account.name,
                "aud": "https://example.com",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=5)).timestamp()),
                "scope": "maintenance:read unknown:write",
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signing_input_encoded = base64.b64encode(signing_input).decode("ascii")

    response = client.post(
        "/api/service_accounts/signatures",
        json={
            "signingInput": signing_input_encoded,
            "signingInputEncoding": "base64",
            "kid": issued.kid,
        },
        headers={"Authorization": f"ApiKey {api_key_value}"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"] == "The signing request scope is not permitted."
