"""証明書APIの結合テスト"""
from __future__ import annotations

import base64
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from core.db import db
from core.models.user import Permission, Role, User
from features.certs.infrastructure.models import CertificateGroupEntity


def _login_admin(client):
    password = "password123"
    user = User(email="admin@example.com", username="admin")
    user.set_password(password)

    manage_perm = Permission.query.filter_by(code="certificate:manage").first()
    if manage_perm is None:
        manage_perm = Permission(code="certificate:manage")

    sign_perm = Permission.query.filter_by(code="certificate:sign").first()
    if sign_perm is None:
        sign_perm = Permission(code="certificate:sign")

    role = Role(name="admin-test")
    role.permissions.extend([manage_perm, sign_perm])
    user.roles.append(role)

    db.session.add_all([manage_perm, sign_perm, role, user])
    db.session.commit()

    response = client.post(
        "/auth/login",
        data={"email": user.email, "password": password},
        follow_redirects=True,
    )
    assert response.status_code == 200


def _create_group() -> CertificateGroupEntity:
    group = CertificateGroupEntity(
        group_code="server_signing_default",
        display_name="Server Signing",
        auto_rotate=True,
        rotation_threshold_days=30,
        key_type="RSA",
        key_size=2048,
        subject={"C": "JP", "O": "Example", "CN": "AuthServer"},
        usage_type="server_signing",
    )
    db.session.add(group)
    db.session.commit()
    return group


def _login_user_without_permission(client):
    password = "password123"
    user = User(email="member@example.com", username="member")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    response = client.post(
        "/auth/login",
        data={"email": user.email, "password": password},
        follow_redirects=True,
    )
    assert response.status_code == 200


def test_group_management_endpoints(app_context):
    client = app_context.test_client()
    _login_admin(client)

    invalid_resp = client.post(
        "/api/certs/groups",
        json={
            "groupCode": "Invalid-Group",
            "displayName": "Invalid Group",
            "usageType": "server_signing",
            "keyType": "RSA",
            "keySize": 2048,
            "autoRotate": True,
            "rotationThresholdDays": 30,
            "subject": {"CN": "example.invalid"},
        },
    )
    assert invalid_resp.status_code == 400

    create_resp = client.post(
        "/api/certs/groups",
        json={
            "groupCode": "test-group",
            "displayName": "Test Group",
            "usageType": "server_signing",
            "keyType": "RSA",
            "keySize": 2048,
            "autoRotate": True,
            "rotationThresholdDays": 30,
            "subject": {"CN": "example.test"},
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.get_json()["group"]
    assert created["groupCode"] == "test-group"

    list_resp = client.get("/api/certs/groups")
    assert list_resp.status_code == 200
    groups = list_resp.get_json()["groups"]
    assert any(item["groupCode"] == "test-group" for item in groups)

    update_resp = client.put(
        "/api/certs/groups/test-group",
        json={
            "displayName": "Updated Group",
            "usageType": "server_signing",
            "keyType": "RSA",
            "keySize": 4096,
            "autoRotate": False,
            "rotationThresholdDays": 60,
            "subject": {"CN": "updated.example"},
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.get_json()["group"]
    assert updated["displayName"] == "Updated Group"
    assert updated["autoRotate"] is False

    delete_resp = client.delete("/api/certs/groups/test-group")
    assert delete_resp.status_code == 200

def test_generate_sign_and_jwks_flow(app_context):
    client = app_context.test_client()
    _login_admin(client)

    group = _create_group()

    generate_resp = client.post(
        "/api/certs/generate",
        json={
            "subject": {"C": "JP", "O": "Example", "CN": "service-1"},
            "usageType": "server_signing",
            "keyType": "RSA",
            "keyBits": 2048,
            "makeCsr": True,
            "keyUsage": ["digitalSignature", "keyEncipherment"],
        },
    )
    assert generate_resp.status_code == 200
    generated = generate_resp.get_json()

    assert generated["csrPem"]
    assert generated["privateKeyPem"].startswith("-----BEGIN PRIVATE KEY-----")

    csr = x509.load_pem_x509_csr(generated["csrPem"].encode("utf-8"))
    subject_map = {attr.oid: attr.value for attr in csr.subject}
    assert subject_map[x509.oid.NameOID.COMMON_NAME] == "service-1"
    assert subject_map[x509.oid.NameOID.ORGANIZATION_NAME] == "Example"
    assert subject_map[x509.oid.NameOID.COUNTRY_NAME] == "JP"

    sign_resp = client.post(
        "/api/certs/sign",
        json={
            "csrPem": generated["csrPem"],
            "usageType": "server_signing",
            "days": 30,
            "keyUsage": ["digitalSignature", "keyEncipherment"],
            "groupCode": group.group_code,
        },
    )
    assert sign_resp.status_code == 200
    signed = sign_resp.get_json()
    certificate_pem = signed["certificatePem"]
    certificate = x509.load_pem_x509_certificate(certificate_pem.encode("utf-8"))

    assert (
        certificate.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("utf-8")
        == generated["publicKeyPem"]
    )

    keys_resp = client.get(f"/api/keys/{group.group_code}")
    assert keys_resp.status_code == 200
    keys_payload = keys_resp.get_json()
    assert keys_payload["keys"]
    assert keys_payload["keys"][0]["kid"] == signed["kid"]

    jwks_resp = client.get(f"/api/.well-known/jwks/{group.group_code}.json")
    assert jwks_resp.status_code == 200
    jwks = jwks_resp.get_json()
    assert jwks["keys"]
    assert jwks["keys"][0]["kid"] == signed["kid"]

    list_resp = client.get("/api/certs")
    assert list_resp.status_code == 200
    listed = list_resp.get_json()
    assert any(item["kid"] == signed["kid"] for item in listed["certificates"])

    detail_resp = client.get(f"/api/certs/{signed['kid']}")
    assert detail_resp.status_code == 200
    detail = detail_resp.get_json()["certificate"]
    assert detail["kid"] == signed["kid"]
    assert detail["certificatePem"].startswith("-----BEGIN CERTIFICATE-----")

    revoke_resp = client.post(
        f"/api/certs/{signed['kid']}/revoke",
        json={"reason": "compromised"},
    )
    assert revoke_resp.status_code == 200
    revoked = revoke_resp.get_json()["certificate"]
    assert revoked["revokedAt"] is not None
    assert revoked["revocationReason"] == "compromised"

    detail_after_resp = client.get(f"/api/certs/{signed['kid']}")
    assert detail_after_resp.status_code == 200
    detail_after = detail_after_resp.get_json()["certificate"]
    assert detail_after["revokedAt"] is not None

    search_resp = client.get("/api/certs/search", query_string={"kid": signed["kid"]})
    assert search_resp.status_code == 200
    search_payload = search_resp.get_json()
    assert search_payload["total"] >= 1


def test_latest_key_endpoint_returns_only_newest_key(app_context):
    client = app_context.test_client()
    _login_admin(client)

    group = _create_group()

    def _sign_certificate(common_name: str) -> dict:
        generate_resp = client.post(
            "/api/certs/generate",
            json={
                "subject": {"C": "JP", "O": "Example", "CN": common_name},
                "usageType": "server_signing",
                "keyType": "RSA",
                "keyBits": 2048,
                "makeCsr": True,
                "keyUsage": ["digitalSignature", "keyEncipherment"],
            },
        )
        assert generate_resp.status_code == 200
        generated = generate_resp.get_json()

        sign_resp = client.post(
            "/api/certs/sign",
            json={
                "csrPem": generated["csrPem"],
                "usageType": "server_signing",
                "days": 30,
                "keyUsage": ["digitalSignature", "keyEncipherment"],
                "groupCode": group.group_code,
            },
        )
        assert sign_resp.status_code == 200
        return sign_resp.get_json()

    first_signed = _sign_certificate("service-1")
    second_signed = _sign_certificate("service-2")

    latest_resp = client.get(f"/api/keys/{group.group_code}")
    assert latest_resp.status_code == 200
    latest_payload = latest_resp.get_json()
    assert latest_payload["keys"] == [second_signed["jwk"]]

    jwks_resp = client.get(f"/api/.well-known/jwks/{group.group_code}.json")
    assert jwks_resp.status_code == 200
    jwks_payload = jwks_resp.get_json()["keys"]
    assert jwks_payload[0]["kid"] == second_signed["kid"]
    assert any(key["kid"] == first_signed["kid"] for key in jwks_payload)


def test_generate_rejects_unknown_usage(app_context):
    client = app_context.test_client()
    _login_admin(client)

    resp = client.post(
        "/api/certs/generate",
        json={
            "subject": {"CN": "invalid"},
            "usageType": "unknown_usage",
        },
    )
    assert resp.status_code == 400
    error = resp.get_json()
    assert "error" in error


def test_generate_and_sign_ec_certificate(app_context):
    client = app_context.test_client()
    _login_admin(client)

    group = _create_group()

    generate_resp = client.post(
        "/api/certs/generate",
        json={
            "subject": {"C": "JP", "O": "Example", "CN": "ec-service"},
            "usageType": "server_signing",
            "keyType": "EC",
            "makeCsr": True,
        },
    )
    assert generate_resp.status_code == 200
    generated = generate_resp.get_json()

    private_key = serialization.load_pem_private_key(
        generated["privateKeyPem"].encode("utf-8"), password=None
    )
    assert isinstance(private_key, ec.EllipticCurvePrivateKey)

    csr = x509.load_pem_x509_csr(generated["csrPem"].encode("utf-8"))
    public_key = csr.public_key()
    assert isinstance(public_key, ec.EllipticCurvePublicKey)
    assert public_key.curve.name == "secp256r1"

    sign_resp = client.post(
        "/api/certs/sign",
        json={
            "csrPem": generated["csrPem"],
            "usageType": "server_signing",
            "days": 30,
            "groupCode": group.group_code,
        },
    )
    assert sign_resp.status_code == 200
    signed = sign_resp.get_json()

    certificate = x509.load_pem_x509_certificate(signed["certificatePem"].encode("utf-8"))
    cert_public_key = certificate.public_key()
    assert isinstance(cert_public_key, ec.EllipticCurvePublicKey)
    assert cert_public_key.curve.name == "secp256r1"

    jwk = signed["jwk"]
    assert jwk["kty"] == "EC"
    assert jwk["crv"] == "P-256"


def test_group_certificate_issue_and_listing(app_context):
    client = app_context.test_client()
    _login_admin(client)

    group = _create_group()

    issue_resp = client.post(
        f"/api/certs/groups/{group.group_code}/certificates",
        json={
            "validDays": 90,
            "subject": {"CN": "api-service"},
            "keyUsage": ["digitalSignature"],
        },
    )
    assert issue_resp.status_code == 201
    issued_payload = issue_resp.get_json()["certificate"]
    assert issued_payload["groupCode"] == group.group_code
    assert issued_payload["usageType"] == "server_signing"
    assert issued_payload["certificatePem"].startswith("-----BEGIN CERTIFICATE-----")

    list_resp = client.get(f"/api/certs/groups/{group.group_code}/certificates")
    assert list_resp.status_code == 200
    body = list_resp.get_json()
    assert body["group"]["groupCode"] == group.group_code
    kids = [item["kid"] for item in body["certificates"]]
    assert issued_payload["kid"] in kids


def test_sign_group_payload_api(app_context):
    client = app_context.test_client()
    _login_admin(client)

    group = _create_group()

    issue_resp = client.post(
        f"/api/certs/groups/{group.group_code}/certificates",
        json={},
    )
    assert issue_resp.status_code == 201
    certificate_payload = issue_resp.get_json()["certificate"]

    payload = b"hello-cert"
    payload_b64 = base64.b64encode(payload).decode("ascii")
    sign_resp = client.post(
        f"/api/keys/{group.group_code}/{certificate_payload['kid']}/sign",
        json={"payload": payload_b64},
    )
    assert sign_resp.status_code == 200
    sign_body = sign_resp.get_json()
    assert sign_body["groupCode"] == group.group_code
    assert sign_body["kid"] == certificate_payload["kid"]
    assert sign_body["hashAlgorithm"] == "SHA256"
    assert sign_body["algorithm"] == "RS256"

    signature = base64.b64decode(sign_body["signature"])
    certificate = x509.load_pem_x509_certificate(
        certificate_payload["certificatePem"].encode("utf-8")
    )
    public_key = certificate.public_key()
    if isinstance(public_key, rsa.RSAPublicKey):
        public_key.verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
    else:
        public_key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))

    payload_urlsafe = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    sign_resp_urlsafe = client.post(
        f"/api/keys/{group.group_code}/{certificate_payload['kid']}/sign",
        json={"payload": payload_urlsafe, "payloadEncoding": "base64url"},
    )
    assert sign_resp_urlsafe.status_code == 200


def test_search_filters_cover_group_usage_and_revocation(app_context):
    client = app_context.test_client()
    _login_admin(client)

    group = _create_group()

    issue_resp = client.post(
        f"/api/certs/groups/{group.group_code}/certificates",
        json={"validDays": 30},
    )
    assert issue_resp.status_code == 201
    issued = issue_resp.get_json()["certificate"]

    revoke_resp = client.post(
        f"/api/certs/{issued['kid']}/revoke",
        json={"reason": "test"},
    )
    assert revoke_resp.status_code == 200

    search_resp = client.get(
        "/api/certs/search",
        query_string={
            "group_code": group.group_code,
            "usage_type": "server_signing",
            "revoked": "true",
        },
    )
    assert search_resp.status_code == 200
    payload = search_resp.get_json()
    assert payload["total"] == 1
    assert payload["certificates"][0]["kid"] == issued["kid"]
    assert payload["certificates"][0]["revokedAt"] is not None


def test_requires_certificate_manage_permission(app_context):
    client = app_context.test_client()
    _login_user_without_permission(client)

    response = client.get("/api/certs/groups")
    assert response.status_code == 403
    error = response.get_json()
    assert error["error"] == "Forbidden"


def test_keys_endpoints_require_sign_permission(app_context):
    client = app_context.test_client()
    _login_user_without_permission(client)

    list_resp = client.get("/api/keys/example-group")
    assert list_resp.status_code == 403

    sign_resp = client.post(
        "/api/keys/example-group/example-kid/sign",
        json={"payload": base64.b64encode(b"data").decode("ascii")},
    )
    assert sign_resp.status_code == 403


def test_list_certificates_rejects_invalid_usage(app_context):
    client = app_context.test_client()
    _login_admin(client)

    resp = client.get("/api/certs", query_string={"usage": "unknown"})
    assert resp.status_code == 400
    error = resp.get_json()
    assert "error" in error
