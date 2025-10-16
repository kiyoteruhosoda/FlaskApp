"""証明書UI向けサービス"""
from __future__ import annotations

from datetime import datetime

from flask import Flask, current_app

from features.certs.domain.usage import UsageType

from .api_client import (
    CertificateDetail,
    CertificateGroupData,
    CertificateSearchResult,
    CertificateSummary,
    CertsApiClient,
    GeneratedMaterial,
    IssuedCertificateWithPrivateKey,
    SignedCertificate,
    SignedPayload,
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

    def list_groups(self) -> list[CertificateGroupData]:
        return self._client.list_groups()

    def create_group(
        self,
        *,
        group_code: str,
        display_name: str | None,
        usage_type: UsageType,
        key_type: str,
        key_curve: str | None,
        key_size: int | None,
        auto_rotate: bool,
        rotation_threshold_days: int,
        subject: dict[str, str],
    ) -> CertificateGroupData:
        return self._client.create_group(
            group_code=group_code,
            display_name=display_name,
            usage_type=usage_type,
            key_type=key_type,
            key_curve=key_curve,
            key_size=key_size,
            auto_rotate=auto_rotate,
            rotation_threshold_days=rotation_threshold_days,
            subject=subject,
        )

    def update_group(
        self,
        group_code: str,
        *,
        display_name: str | None,
        usage_type: UsageType,
        key_type: str,
        key_curve: str | None,
        key_size: int | None,
        auto_rotate: bool,
        rotation_threshold_days: int,
        subject: dict[str, str],
    ) -> CertificateGroupData:
        return self._client.update_group(
            group_code,
            display_name=display_name,
            usage_type=usage_type,
            key_type=key_type,
            key_curve=key_curve,
            key_size=key_size,
            auto_rotate=auto_rotate,
            rotation_threshold_days=rotation_threshold_days,
            subject=subject,
        )

    def delete_group(self, group_code: str) -> None:
        self._client.delete_group(group_code)

    def list_group_certificates(
        self,
        group_code: str,
    ) -> tuple[CertificateGroupData, list[CertificateSummary]]:
        return self._client.list_group_certificates(group_code)

    def issue_certificate_for_group(
        self,
        group_code: str,
        *,
        subject_overrides: dict[str, str] | None = None,
        valid_days: int | None = None,
        key_usage: list[str] | None = None,
    ) -> IssuedCertificateWithPrivateKey:
        return self._client.issue_certificate_for_group(
            group_code,
            subject_overrides=subject_overrides,
            valid_days=valid_days,
            key_usage=key_usage,
        )

    def sign_group_payload(
        self,
        group_code: str,
        *,
        payload: bytes,
        kid: str | None = None,
        hash_algorithm: str = "SHA256",
    ) -> SignedPayload:
        return self._client.sign_group_payload(
            group_code,
            payload=payload,
            kid=kid,
            hash_algorithm=hash_algorithm,
        )

    def revoke_certificate_in_group(
        self,
        group_code: str,
        kid: str,
        *,
        reason: str | None = None,
    ) -> CertificateDetail:
        return self._client.revoke_certificate_in_group(group_code, kid, reason=reason)

    def search_certificates(
        self,
        *,
        kid: str | None = None,
        group_code: str | None = None,
        usage_type: UsageType | None = None,
        subject: str | None = None,
        issued_from: datetime | None = None,
        issued_to: datetime | None = None,
        expires_from: datetime | None = None,
        expires_to: datetime | None = None,
        revoked: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CertificateSearchResult:
        return self._client.search_certificates(
            kid=kid,
            group_code=group_code,
            usage_type=usage_type,
            subject=subject,
            issued_from=issued_from,
            issued_to=issued_to,
            expires_from=expires_from,
            expires_to=expires_to,
            revoked=revoked,
            limit=limit,
            offset=offset,
        )


__all__ = ["CertificateUiService"]
