"""証明書APIの結合テスト"""
from __future__ import annotations

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from core.db import db
from core.models.user import Permission, Role, User
from features.certs.infrastructure.models import CertificateGroupEntity


def _login_admin(client):
    password = "password123"
    user = User(email="admin@example.com", username="admin")
    user.set_password(password)

    perm = Permission.query.filter_by(code="certificate:manage").first()
    if perm is None:
        perm = Permission(code="certificate:manage")

    role = Role(name="admin-test")
    role.permissions.append(perm)
    user.roles.append(role)

    db.session.add_all([perm, role, user])
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


def test_group_management_endpoints(app_context):
    client = app_context.test_client()
    _login_admin(client)

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


def test_list_certificates_rejects_invalid_usage(app_context):
    client = app_context.test_client()
    _login_admin(client)

    resp = client.get("/api/certs", query_string={"usage": "unknown"})
    assert resp.status_code == 400
    error = resp.get_json()
    assert "error" in error
