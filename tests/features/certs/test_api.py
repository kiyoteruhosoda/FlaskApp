"""証明書APIの結合テスト"""
from __future__ import annotations

from cryptography import x509
from cryptography.hazmat.primitives import serialization


def test_generate_sign_and_jwks_flow(app_context):
    client = app_context.test_client()

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

    jwks_resp = client.get("/api/.well-known/jwks/server.json")
    assert jwks_resp.status_code == 200
    jwks = jwks_resp.get_json()
    assert jwks["keys"]
    assert jwks["keys"][0]["kid"] == signed["kid"]


def test_generate_rejects_unknown_usage(app_context):
    client = app_context.test_client()

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
