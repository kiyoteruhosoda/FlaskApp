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


@pytest.mark.usefixtures("app_context")
def test_service_account_end_to_end_login_flow(app_context):
    group = CertificateGroupEntity(
        group_code="client-signing",
        display_name="Client Signing",
        auto_rotate=False,
        rotation_threshold_days=30,
        key_type="EC",
        key_curve="P-256",
        key_size=None,
        subject={"CN": "Client Signing"},
        usage_type=UsageType.CLIENT_SIGNING.value,
    )
    db.session.add(group)
    db.session.commit()

    issued = IssueCertificateForGroupUseCase().execute(group.group_code)
    jwks_payload = ListJwksUseCase().execute(group.group_code)
    assert any(key.get("kid") == issued.kid for key in jwks_payload.get("keys", []))

    account = ServiceAccountService.create_account(
        name="maintenance-bot",
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

    app = app_context

    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    client = app.test_client()

    now = datetime.now(timezone.utc)
    audience = "http://localhost/api/maintenance"
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
                "scope": "maintenance:read",
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
