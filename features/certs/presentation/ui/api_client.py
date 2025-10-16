"""APIクライアント: 証明書機能"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any
from urllib.parse import urljoin

import requests
from cryptography import x509
from cryptography.x509.oid import NameOID
from flask import Flask, current_app, has_request_context, request, url_for

from features.certs.domain.usage import UsageType
from webapp.auth.utils import log_requests_and_send
from shared.application.api_urls import get_api_base_url


class CertsApiClientError(RuntimeError):
    """API呼び出しの失敗を表す例外"""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(slots=True)
class GeneratedMaterial:
    private_key_pem: str
    public_key_pem: str
    csr_pem: str | None
    thumbprint: str
    usage_type: UsageType


@dataclass(slots=True)
class SignedCertificate:
    certificate_pem: str
    kid: str
    jwk: dict[str, Any]
    usage_type: UsageType


@dataclass(slots=True)
class CertificateSummary:
    kid: str
    usage_type: UsageType
    issued_at: datetime | None
    revoked_at: datetime | None
    revocation_reason: str | None
    subject: str

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def common_name(self) -> str | None:
        if not self.subject:
            return None
        try:
            name = x509.Name.from_rfc4514_string(self.subject)
        except ValueError:
            return None
        for attribute in name:
            if attribute.oid == NameOID.COMMON_NAME:
                return attribute.value
        return None


@dataclass(slots=True)
class CertificateDetail(CertificateSummary):
    certificate_pem: str
    jwk: dict[str, Any]
    issuer: str
    not_before: datetime | None
    not_after: datetime | None


class CertsApiClient:
    """UIから証明書APIを利用するための簡易クライアント"""

    def __init__(self, app: Flask | None = None) -> None:
        self._app = app or current_app._get_current_object()
        self._timeout = self._app.config.get("CERTS_API_TIMEOUT", 10)

    def list_certificates(self, usage: UsageType | None = None) -> list[CertificateSummary]:
        params = {"usage": usage.value} if usage else None
        payload = self._dispatch("GET", "certs_api.list_certificates", params=params)
        certificates = payload.get("certificates", [])
        return [self._parse_summary(item) for item in certificates]

    def get_certificate(self, kid: str) -> CertificateDetail:
        payload = self._dispatch("GET", "certs_api.get_certificate", kid=kid)
        certificate = payload.get("certificate") or {}
        return self._parse_detail(certificate)

    def revoke_certificate(self, kid: str, reason: str | None = None) -> CertificateDetail:
        payload = self._dispatch(
            "POST",
            "certs_api.revoke_certificate",
            json={"reason": reason} if reason else None,
            kid=kid,
        )
        certificate = payload.get("certificate") or {}
        return self._parse_detail(certificate)

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
        payload = self._dispatch(
            "POST",
            "certs_api.generate_certificate_material",
            json={
                "subject": subject,
                "keyType": key_type,
                "keyBits": key_bits,
                "makeCsr": make_csr,
                "usageType": usage_type.value,
                "keyUsage": key_usage,
            },
        )
        return GeneratedMaterial(
            private_key_pem=payload.get("privateKeyPem", ""),
            public_key_pem=payload.get("publicKeyPem", ""),
            csr_pem=payload.get("csrPem"),
            thumbprint=payload.get("thumbprint", ""),
            usage_type=usage_type,
        )

    def sign_certificate(
        self,
        *,
        csr_pem: str,
        usage_type: UsageType,
        days: int,
        is_ca: bool,
        key_usage: list[str],
    ) -> SignedCertificate:
        payload = self._dispatch(
            "POST",
            "certs_api.sign_certificate",
            json={
                "csrPem": csr_pem,
                "usageType": usage_type.value,
                "days": days,
                "isCa": is_ca,
                "keyUsage": key_usage,
            },
        )
        return SignedCertificate(
            certificate_pem=payload.get("certificatePem", ""),
            kid=payload.get("kid", ""),
            jwk=payload.get("jwk", {}),
            usage_type=usage_type,
        )

    def list_jwks(self, usage: UsageType) -> dict[str, Any]:
        return self._dispatch("GET", "certs_api.jwks", usage=usage.value)

    def _dispatch(
        self,
        method: str,
        endpoint: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        **url_params: Any,
    ) -> dict[str, Any]:
        url = self._build_url(endpoint, **url_params)
        headers = self._build_headers()

        try:
            response = log_requests_and_send(
                method.lower(),
                url,
                headers=headers,
                params=params,
                json_data=json,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise CertsApiClientError(str(exc), HTTPStatus.BAD_GATEWAY) from exc

        if response.status_code >= HTTPStatus.BAD_REQUEST:
            raise CertsApiClientError(
                _extract_error_message(response), response.status_code
            )

        try:
            data = response.json()
        except ValueError:
            data = None
        return data or {}

    def _build_url(self, endpoint: str, **url_params: Any) -> str:
        path = url_for(endpoint, **url_params)
        base_url = self._resolve_base_url()
        return urljoin(base_url.rstrip("/") + "/", path)

    def _resolve_base_url(self) -> str:
        env_base_url = get_api_base_url()
        if env_base_url:
            return env_base_url

        if has_request_context():
            return request.url_root
        raise CertsApiClientError(
            "API_BASE_URL is not configured", HTTPStatus.INTERNAL_SERVER_ERROR
        )

    def _build_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if has_request_context() and request.headers.get("Authorization"):
            headers["Authorization"] = request.headers["Authorization"]
        cookie_header = self._build_cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers

    def _build_cookie_header(self) -> str | None:
        if not has_request_context():
            return None
        cookies = []
        for key, value in request.cookies.items():
            cookies.append(f"{key}={value}")
        if not cookies:
            return None
        return "; ".join(cookies)

    def _parse_summary(self, payload: dict[str, Any]) -> CertificateSummary:
        return CertificateSummary(
            kid=str(payload.get("kid", "")),
            usage_type=_parse_usage(payload.get("usageType")),
            issued_at=_parse_datetime(payload.get("issuedAt")),
            revoked_at=_parse_datetime(payload.get("revokedAt")),
            revocation_reason=payload.get("revocationReason"),
            subject=str(payload.get("subject", "")),
        )

    def _parse_detail(self, payload: dict[str, Any]) -> CertificateDetail:
        summary = self._parse_summary(payload)
        return CertificateDetail(
            kid=summary.kid,
            usage_type=summary.usage_type,
            issued_at=summary.issued_at,
            revoked_at=summary.revoked_at,
            revocation_reason=summary.revocation_reason,
            subject=summary.subject,
            certificate_pem=str(payload.get("certificatePem", "")),
            jwk=payload.get("jwk", {}),
            issuer=str(payload.get("issuer", "")),
            not_before=_parse_datetime(payload.get("notBefore")),
            not_after=_parse_datetime(payload.get("notAfter")),
        )


def _parse_usage(value: str | None) -> UsageType:
    if value is None:
        raise CertsApiClientError("usageTypeがレスポンスに含まれていません", HTTPStatus.INTERNAL_SERVER_ERROR)
    try:
        return UsageType.from_str(value)
    except ValueError as exc:  # pragma: no cover - 不正値は想定外
        raise CertsApiClientError(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR) from exc


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:  # pragma: no cover - 不正値は想定外
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _extract_error_message(response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and payload.get("error"):
        return str(payload["error"])
    text = getattr(response, "text", "")
    if not text and hasattr(response, "get_data"):
        text = response.get_data(as_text=True)
    return text or "API request failed"


__all__ = [
    "CertsApiClient",
    "CertsApiClientError",
    "GeneratedMaterial",
    "SignedCertificate",
    "CertificateSummary",
    "CertificateDetail",
]
