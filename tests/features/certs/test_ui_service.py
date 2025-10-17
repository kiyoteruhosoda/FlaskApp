"""UIサービス層のテスト"""
from __future__ import annotations

from http import HTTPStatus

import pytest

from features.certs.domain.usage import UsageType
from features.certs.presentation.ui.api_client import (
    CertsApiClientError,
    CertificateDetail,
    CertificateGroupData,
    CertificateSearchResult,
    CertificateSummary,
    GeneratedMaterial,
    IssuedCertificateWithPrivateKey,
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
                expires_at=None,
                revoked_at=None,
                revocation_reason=None,
                subject="CN=example",
                group_code="server",
                auto_rotated_from_kid=None,
            )
        ]

    def get_certificate(self, kid):
        self.calls.append(("get_certificate", (kid,), {}))
        return CertificateDetail(
            kid=kid,
            usage_type=UsageType.SERVER_SIGNING,
            issued_at=None,
            expires_at=None,
            revoked_at=None,
            revocation_reason=None,
            subject="CN=sub",
            group_code="server",
            auto_rotated_from_kid=None,
            certificate_pem="pem",
            jwk={},
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
            group_code="server",
        )

    def list_jwks(self, group_code):
        self.calls.append(("list_jwks", (group_code,), {}))
        return {"keys": []}

    def list_groups(self):
        self.calls.append(("list_groups", tuple(), {}))
        return [
            CertificateGroupData(
                group_code="group-a",
                display_name="Group A",
                usage_type=UsageType.SERVER_SIGNING,
                key_type="RSA",
                key_curve=None,
                key_size=2048,
                auto_rotate=True,
                rotation_threshold_days=30,
                subject={"CN": "example"},
                key_usage=("digitalSignature",),
                created_at=None,
                updated_at=None,
            )
        ]

    def create_group(self, **kwargs):
        self.calls.append(("create_group", tuple(), kwargs))
        return CertificateGroupData(
            group_code=kwargs["group_code"],
            display_name=kwargs.get("display_name"),
            usage_type=kwargs["usage_type"],
            key_type=kwargs["key_type"],
            key_curve=kwargs.get("key_curve"),
            key_size=kwargs.get("key_size"),
            auto_rotate=kwargs.get("auto_rotate", True),
            rotation_threshold_days=kwargs.get("rotation_threshold_days", 30),
            subject=kwargs["subject"],
            key_usage=tuple(kwargs.get("key_usage") or []),
            created_at=None,
            updated_at=None,
        )

    def update_group(self, group_code, **kwargs):
        self.calls.append(("update_group", (group_code,), kwargs))
        return CertificateGroupData(
            group_code=group_code,
            display_name=kwargs.get("display_name"),
            usage_type=kwargs["usage_type"],
            key_type=kwargs["key_type"],
            key_curve=kwargs.get("key_curve"),
            key_size=kwargs.get("key_size"),
            auto_rotate=kwargs.get("auto_rotate", True),
            rotation_threshold_days=kwargs.get("rotation_threshold_days", 30),
            subject=kwargs["subject"],
            key_usage=tuple(kwargs.get("key_usage") or []),
            created_at=None,
            updated_at=None,
        )

    def delete_group(self, group_code):
        self.calls.append(("delete_group", (group_code,), {}))

    def list_group_certificates(self, group_code):
        self.calls.append(("list_group_certificates", (group_code,), {}))
        group = CertificateGroupData(
            group_code=group_code,
            display_name="Group",
            usage_type=UsageType.SERVER_SIGNING,
            key_type="RSA",
            key_curve=None,
            key_size=2048,
            auto_rotate=True,
            rotation_threshold_days=30,
            subject={"CN": "example"},
            key_usage=("digitalSignature",),
            created_at=None,
            updated_at=None,
        )
        certificates = [
            CertificateSummary(
                kid="kid",
                usage_type=UsageType.SERVER_SIGNING,
                issued_at=None,
                expires_at=None,
                revoked_at=None,
                revocation_reason=None,
                subject="CN=example",
                group_code=group_code,
                auto_rotated_from_kid=None,
            )
        ]
        return group, certificates

    def issue_certificate_for_group(self, group_code, **kwargs):
        self.calls.append(("issue_certificate_for_group", (group_code,), kwargs))
        return IssuedCertificateWithPrivateKey(
            kid="kid",
            certificate_pem="pem",
            private_key_pem="priv",
            jwk={},
            usage_type=UsageType.SERVER_SIGNING,
            group_code=group_code,
        )

    def revoke_certificate_in_group(self, group_code, kid, **kwargs):
        self.calls.append(("revoke_certificate_in_group", (group_code, kid), kwargs))
        return CertificateDetail(
            kid=kid,
            usage_type=UsageType.SERVER_SIGNING,
            issued_at=None,
            expires_at=None,
            revoked_at=None,
            revocation_reason=None,
            subject="CN=sub",
            group_code=group_code,
            auto_rotated_from_kid=None,
            certificate_pem="pem",
            jwk={},
            issuer="issuer",
            not_before=None,
            not_after=None,
        )

    def search_certificates(self, **kwargs):
        self.calls.append(("search_certificates", tuple(), kwargs))
        return CertificateSearchResult(
            total=1,
            certificates=[
                CertificateSummary(
                    kid="kid",
                    usage_type=UsageType.SERVER_SIGNING,
                    issued_at=None,
                    expires_at=None,
                    revoked_at=None,
                    revocation_reason=None,
                    subject="CN=example",
                    group_code=kwargs.get("group_code"),
                    auto_rotated_from_kid=None,
                )
            ],
            limit=50,
            offset=0,
        )


def test_service_delegates_to_client(app_context):
    client = _DummyClient()
    service = CertificateUiService(app_context, client=client)

    service.list_certificates(UsageType.SERVER_SIGNING, group_code="server")
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
        group_code="server",
    )
    service.list_jwks("server")
    service.list_groups()
    service.create_group(
        group_code="new",
        display_name="New",
        usage_type=UsageType.SERVER_SIGNING,
        key_type="RSA",
        key_curve=None,
        key_size=2048,
        auto_rotate=True,
        rotation_threshold_days=30,
        subject={"CN": "new"},
        key_usage=["digitalSignature"],
    )
    service.update_group(
        "group-a",
        display_name="New",
        usage_type=UsageType.SERVER_SIGNING,
        key_type="RSA",
        key_curve=None,
        key_size=2048,
        auto_rotate=False,
        rotation_threshold_days=45,
        subject={"CN": "changed"},
        key_usage=["digitalSignature"],
    )
    service.delete_group("group-a")
    service.list_group_certificates("group-a")
    service.issue_certificate_for_group("group-a")
    service.revoke_certificate_in_group("group-a", "kid")
    service.search_certificates(kid="kid")

    call_names = [name for name, *_ in client.calls]
    assert call_names == [
        "list_certificates",
        "get_certificate",
        "revoke_certificate",
        "get_certificate",
        "generate_material",
        "sign_certificate",
        "list_jwks",
        "list_groups",
        "create_group",
        "update_group",
        "delete_group",
        "list_group_certificates",
        "issue_certificate_for_group",
        "revoke_certificate_in_group",
        "search_certificates",
    ]


def test_service_raises_api_errors(app_context):
    class ErrorClient(_DummyClient):
        def list_certificates(self, *args, **kwargs):
            raise CertsApiClientError("boom", HTTPStatus.BAD_GATEWAY)

    client = ErrorClient()
    service = CertificateUiService(app_context, client=client)

    with pytest.raises(CertsApiClientError):
        service.list_certificates()
