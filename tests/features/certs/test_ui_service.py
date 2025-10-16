"""UIサービス層のテスト"""
from __future__ import annotations

from http import HTTPStatus

import pytest

from features.certs.domain.usage import UsageType
from features.certs.presentation.ui.api_client import (
    CertsApiClientError,
    CertificateDetail,
    CertificateSummary,
    GeneratedMaterial,
    SignedCertificate,
)
from features.certs.presentation.ui.services import CertificateUiService


class _DummyClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def list_certificates(self, *args, **kwargs):
        self.calls.append(("list_certificates", args, kwargs))
        return [
            CertificateSummary(
                kid="kid",
                usage_type=UsageType.SERVER_SIGNING,
                issued_at=None,
                revoked_at=None,
                revocation_reason=None,
            )
        ]

    def get_certificate(self, kid):
        self.calls.append(("get_certificate", (kid,), {}))
        return CertificateDetail(
            kid=kid,
            usage_type=UsageType.SERVER_SIGNING,
            issued_at=None,
            revoked_at=None,
            revocation_reason=None,
            certificate_pem="pem",
            jwk={},
            subject="sub",
            issuer="issuer",
            not_before=None,
            not_after=None,
        )

    def revoke_certificate(self, kid, reason=None):
        self.calls.append(("revoke_certificate", (kid,), {"reason": reason}))
        return self.get_certificate(kid)

    def generate_material(self, **kwargs):
        self.calls.append(("generate_material", tuple(), kwargs))
        return GeneratedMaterial(
            private_key_pem="priv",
            public_key_pem="pub",
            csr_pem="csr",
            thumbprint="thumb",
            usage_type=UsageType.SERVER_SIGNING,
        )

    def sign_certificate(self, **kwargs):
        self.calls.append(("sign_certificate", tuple(), kwargs))
        return SignedCertificate(
            certificate_pem="pem",
            kid="kid",
            jwk={},
            usage_type=UsageType.SERVER_SIGNING,
        )

    def list_jwks(self, usage):
        self.calls.append(("list_jwks", (usage,), {}))
        return {"keys": []}


def test_service_delegates_to_client(app_context):
    client = _DummyClient()
    service = CertificateUiService(app_context, client=client)

    service.list_certificates(UsageType.SERVER_SIGNING)
    service.get_certificate("kid")
    service.revoke_certificate("kid", "reason")
    service.generate_material(
        subject={"CN": "example"},
        key_type="RSA",
        key_bits=2048,
        make_csr=True,
        usage_type=UsageType.SERVER_SIGNING,
        key_usage=["digitalSignature"],
    )
    service.sign_certificate(
        csr_pem="csr",
        usage_type=UsageType.SERVER_SIGNING,
        days=365,
        is_ca=False,
        key_usage=["digitalSignature"],
    )
    service.list_jwks(UsageType.SERVER_SIGNING)

    call_names = [name for name, *_ in client.calls]
    assert call_names == [
        "list_certificates",
        "get_certificate",
        "revoke_certificate",
        "get_certificate",
        "generate_material",
        "sign_certificate",
        "list_jwks",
    ]


def test_service_raises_api_errors(app_context):
    class ErrorClient(_DummyClient):
        def list_certificates(self, *args, **kwargs):
            raise CertsApiClientError("boom", HTTPStatus.BAD_GATEWAY)

    client = ErrorClient()
    service = CertificateUiService(app_context, client=client)

    with pytest.raises(CertsApiClientError):
        service.list_certificates()
