from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime, timedelta, timezone

import pytest
from flask import jsonify, request
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from core.db import db
from features.certs.application.dto import SignGroupPayloadInput
from features.certs.application.use_cases import (
    IssueCertificateForGroupUseCase,
    ListJwksUseCase,
    SignGroupPayloadUseCase,
)
from features.certs.domain.usage import UsageType
from features.certs.infrastructure.models import CertificateGroupEntity
from webapp.auth.api_key_auth import require_api_key_scopes
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
        scope_names="maintenance:read",
        active=True,
        allowed_scopes=["maintenance:read"],
    )

    _, api_key_value = ServiceAccountApiKeyService.create_key(
        account.service_account_id,
        scopes="maintenance:read",
        expires_at=None,
        created_by="admin@example.com",
    )

    app = app_context

    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    @app.route("/internal/sign-jws", methods=["POST"])
    @require_api_key_scopes(["maintenance:read"])
    def sign_jws_endpoint():
        payload = request.get_json(silent=True) or {}
        encoded_input = payload.get("signingInput")
        if not isinstance(encoded_input, str) or not encoded_input.strip():
            return jsonify({"error": "signingInput is required"}), 400
        try:
            signing_input_bytes = base64.b64decode(encoded_input.strip(), validate=True)
        except (binascii.Error, ValueError):
            return jsonify({"error": "signingInput must be base64 encoded"}), 400

        sign_input = SignGroupPayloadInput(
            group_code=group.group_code,
            payload=signing_input_bytes,
            kid=issued.kid,
            hash_algorithm="SHA256",
        )
        result = SignGroupPayloadUseCase().execute(sign_input)
        signature_bytes = result.signature
        if result.algorithm.startswith("ES"):
            component_size = int(result.algorithm[2:]) // 8
            r_value, s_value = decode_dss_signature(signature_bytes)
            signature_bytes = r_value.to_bytes(component_size, "big") + s_value.to_bytes(
                component_size, "big"
            )
        signature_segment = _b64url(signature_bytes)
        return jsonify(
            {
                "signature": signature_segment,
                "kid": result.kid,
                "algorithm": result.algorithm,
            }
        )

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
        "/internal/sign-jws",
        json={"signingInput": signing_input_encoded},
        headers={"Authorization": f"ApiKey {api_key_value}"},
    )
    assert sign_response.status_code == 200
    signature_segment = sign_response.get_json()["signature"]

    token = f"{header_segment}.{payload_segment}.{signature_segment}"

    response = client.get(
        "/api/maintenance/ping",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["service_account"] == account.name
