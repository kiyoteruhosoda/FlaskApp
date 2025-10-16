"""証明書UI向けサービス"""
from __future__ import annotations

from flask import Flask, current_app

from features.certs.domain.usage import UsageType

from .api_client import (
    CertsApiClient,
    GeneratedMaterial,
    SignedCertificate,
    CertificateDetail,
    CertificateSummary,
)


class CertificateUiService:
    """UIから証明書APIを利用するサービス"""

    def __init__(
        self,
        app: Flask | None = None,
        *,
        client: CertsApiClient | None = None,
    ) -> None:
        self._app = app or current_app._get_current_object()
        self._client = client or CertsApiClient(self._app)

    def list_certificates(
        self,
        usage: UsageType | None = None,
        *,
        group_code: str | None = None,
    ) -> list[CertificateSummary]:
        return self._client.list_certificates(usage, group_code=group_code)

    def get_certificate(self, kid: str) -> CertificateDetail:
        return self._client.get_certificate(kid)

    def revoke_certificate(self, kid: str, reason: str | None = None) -> CertificateDetail:
        return self._client.revoke_certificate(kid, reason)

    def generate_material(
        self,
        *,
        subject: dict[str, str],
        key_type: str,
        key_bits: int,
        make_csr: bool,
        usage_type: UsageType,
        key_usage: list[str],
    ) -> GeneratedMaterial:
        return self._client.generate_material(
            subject=subject,
            key_type=key_type,
            key_bits=key_bits,
            make_csr=make_csr,
            usage_type=usage_type,
            key_usage=key_usage,
        )

    def sign_certificate(
        self,
        *,
        csr_pem: str,
        usage_type: UsageType,
        days: int,
        is_ca: bool,
        key_usage: list[str],
        group_code: str | None = None,
    ) -> SignedCertificate:
        return self._client.sign_certificate(
            csr_pem=csr_pem,
            usage_type=usage_type,
            days=days,
            is_ca=is_ca,
            key_usage=key_usage,
            group_code=group_code,
        )

    def list_jwks(self, group_code: str) -> dict:
        return self._client.list_jwks(group_code)


__all__ = ["CertificateUiService"]
