"""APIクライアント: 証明書機能"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Any
from urllib.parse import urljoin

import base64
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
    group_code: str | None


@dataclass(slots=True)
class SignedPayload:
    group_code: str
    kid: str
    signature: str
    hash_algorithm: str
    algorithm: str


@dataclass(slots=True)
class CertificateSummary:
    kid: str
    usage_type: UsageType
    issued_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    revocation_reason: str | None
    subject: str
    group_code: str | None
    auto_rotated_from_kid: str | None
    key_usage: list[str] = field(default_factory=list, init=False)
    extended_key_usage: list[str] = field(default_factory=list, init=False)

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


@dataclass(slots=True)
class CertificateGroupData:
    group_code: str
    display_name: str | None
    usage_type: UsageType
    key_type: str
    key_curve: str | None
    key_size: int | None
    auto_rotate: bool
    rotation_threshold_days: int
    subject: dict[str, str]
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(slots=True)
class IssuedCertificateWithPrivateKey:
    kid: str
    certificate_pem: str
    private_key_pem: str
    jwk: dict[str, Any]
    usage_type: UsageType
    group_code: str


@dataclass(slots=True)
class CertificateSearchResult:
    total: int
    certificates: list[CertificateSummary]
    limit: int
    offset: int


class CertsApiClient:
    """UIから証明書APIを利用するための簡易クライアント"""

    DEFAULT_TIMEOUT: float = 10.0

    def __init__(self, app: Flask | None = None) -> None:
        self._app = app or current_app._get_current_object()
        raw_timeout = self._app.config.get("CERTS_API_TIMEOUT", self.DEFAULT_TIMEOUT)
        self._timeout = self._normalise_timeout(raw_timeout)

    @staticmethod
    def _normalise_timeout(value: Any) -> float | tuple[Any, Any] | None:
        """Convert configured timeout into a value accepted by ``requests``.

        ``requests`` treats ``None`` as "wait forever", so we coerce explicit zero
        values to ``None`` while leaving other data types unchanged. This keeps
        backwards compatibility for custom tuple timeouts and ensures that an
        administrator can set ``0`` to disable the timeout entirely.
        """

        if value is None:
            return None
        if isinstance(value, (int, float)):
            return None if value == 0 else float(value)
        if isinstance(value, str):
            stripped = value.strip()
            try:
                numeric = float(stripped)
            except ValueError:
                return value
            if numeric == 0:
                return None
            return numeric
        if isinstance(value, (list, tuple)) and len(value) == 2:
            first, second = value
            coerced_first = CertsApiClient._normalise_timeout(first)
            coerced_second = CertsApiClient._normalise_timeout(second)
            if coerced_first is None or coerced_second is None:
                return None
            if isinstance(coerced_first, (int, float)) and isinstance(
                coerced_second, (int, float)
            ):
                return (float(coerced_first), float(coerced_second))
            return (coerced_first, coerced_second)
        return value

    def list_certificates(
        self,
        usage: UsageType | None = None,
        *,
        group_code: str | None = None,
    ) -> list[CertificateSummary]:
        params: dict[str, Any] | None = {}
        if usage:
            params["usage"] = usage.value
        if group_code:
            params["group"] = group_code
        if not params:
            params = None
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
        group_code: str | None = None,
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
                "groupCode": group_code,
            },
        )
        return SignedCertificate(
            certificate_pem=payload.get("certificatePem", ""),
            kid=payload.get("kid", ""),
            jwk=payload.get("jwk", {}),
            usage_type=usage_type,
            group_code=payload.get("groupCode"),
        )

    def list_jwks(self, group_code: str) -> dict[str, Any]:
        return self._dispatch("GET", "certs_api.jwks", group_code=group_code)

    def list_groups(self) -> list[CertificateGroupData]:
        payload = self._dispatch("GET", "certs_api.list_certificate_groups")
        groups = payload.get("groups", [])
        return [self._parse_group(item) for item in groups]

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
        payload = self._dispatch(
            "POST",
            "certs_api.create_certificate_group",
            json={
                "groupCode": group_code,
                "displayName": display_name,
                "usageType": usage_type.value,
                "keyType": key_type,
                "keyCurve": key_curve,
                "keySize": key_size,
                "autoRotate": auto_rotate,
                "rotationThresholdDays": rotation_threshold_days,
                "subject": subject,
            },
        )
        return self._parse_group(payload.get("group") or {})

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
        payload = self._dispatch(
            "PUT",
            "certs_api.update_certificate_group",
            json={
                "displayName": display_name,
                "usageType": usage_type.value,
                "keyType": key_type,
                "keyCurve": key_curve,
                "keySize": key_size,
                "autoRotate": auto_rotate,
                "rotationThresholdDays": rotation_threshold_days,
                "subject": subject,
            },
            group_code=group_code,
        )
        return self._parse_group(payload.get("group") or {})

    def delete_group(self, group_code: str) -> None:
        self._dispatch("DELETE", "certs_api.delete_certificate_group", group_code=group_code)

    def list_group_certificates(
        self,
        group_code: str,
    ) -> tuple[CertificateGroupData, list[CertificateSummary]]:
        payload = self._dispatch(
            "GET",
            "certs_api.list_group_certificates",
            group_code=group_code,
        )
        group = self._parse_group(payload.get("group") or {})
        certificates_payload = payload.get("certificates", [])
        certificates = [self._parse_summary(item) for item in certificates_payload]
        return group, certificates

    def issue_certificate_for_group(
        self,
        group_code: str,
        *,
        subject_overrides: dict[str, str] | None = None,
        valid_days: int | None = None,
        key_usage: list[str] | None = None,
    ) -> IssuedCertificateWithPrivateKey:
        body: dict[str, Any] = {}
        if subject_overrides:
            body["subject"] = subject_overrides
        if valid_days:
            body["validDays"] = valid_days
        if key_usage is not None:
            body["keyUsage"] = key_usage
        payload = self._dispatch(
            "POST",
            "certs_api.issue_certificate_for_group",
            json=body or None,
            group_code=group_code,
        )
        data = payload.get("certificate") or {}
        return IssuedCertificateWithPrivateKey(
            kid=str(data.get("kid", "")),
            certificate_pem=str(data.get("certificatePem", "")),
            private_key_pem=str(data.get("privateKeyPem", "")),
            jwk=data.get("jwk", {}),
            usage_type=_parse_usage(data.get("usageType")),
            group_code=str(data.get("groupCode", group_code)),
        )

    def sign_group_payload(
        self,
        group_code: str,
        *,
        payload: bytes,
        kid: str | None = None,
        hash_algorithm: str = "SHA256",
    ) -> SignedPayload:
        body: dict[str, Any] = {
            "payload": base64.b64encode(payload).decode("ascii"),
            "hashAlgorithm": hash_algorithm,
        }
        if kid:
            body["kid"] = kid
        response = self._dispatch(
            "POST",
            "certs_api.sign_group_payload",
            group_code=group_code,
            json=body,
        )
        return SignedPayload(
            group_code=str(response.get("groupCode", group_code)),
            kid=str(response.get("kid", "")),
            signature=str(response.get("signature", "")),
            hash_algorithm=str(response.get("hashAlgorithm", hash_algorithm)),
            algorithm=str(response.get("algorithm", "")),
        )

    def revoke_certificate_in_group(
        self,
        group_code: str,
        kid: str,
        *,
        reason: str | None = None,
    ) -> CertificateDetail:
        payload = self._dispatch(
            "POST",
            "certs_api.revoke_certificate_in_group",
            json={"reason": reason} if reason else None,
            group_code=group_code,
            kid=kid,
        )
        certificate = payload.get("certificate") or {}
        return self._parse_detail(certificate)

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
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if kid:
            params["kid"] = kid
        if group_code:
            params["groupCode"] = group_code
        if usage_type:
            params["usageType"] = usage_type.value
        if subject:
            params["subject"] = subject
        if issued_from:
            params["issuedFrom"] = issued_from.isoformat()
        if issued_to:
            params["issuedTo"] = issued_to.isoformat()
        if expires_from:
            params["expiresFrom"] = expires_from.isoformat()
        if expires_to:
            params["expiresTo"] = expires_to.isoformat()
        if revoked is True:
            params["revoked"] = "true"
        elif revoked is False:
            params["revoked"] = "false"

        payload = self._dispatch("GET", "certs_api.search_certificates", params=params)
        certificates_payload = payload.get("certificates", [])
        certificates = [self._parse_summary(item) for item in certificates_payload]
        return CertificateSearchResult(
            total=int(payload.get("total", len(certificates))),
            certificates=certificates,
            limit=int(payload.get("limit", limit)),
            offset=int(payload.get("offset", offset)),
        )

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
        raw_key_usage = payload.get("keyUsage")
        if isinstance(raw_key_usage, (list, tuple)):
            key_usage = [str(item) for item in raw_key_usage if item]
        else:
            key_usage = []
        raw_extended_key_usage = payload.get("extendedKeyUsage")
        if isinstance(raw_extended_key_usage, (list, tuple)):
            extended_key_usage = [str(item) for item in raw_extended_key_usage if item]
        else:
            extended_key_usage = []
        summary = CertificateSummary(
            kid=str(payload.get("kid", "")),
            usage_type=_parse_usage(payload.get("usageType")),
            issued_at=_parse_datetime(payload.get("issuedAt")),
            expires_at=_parse_datetime(payload.get("expiresAt")),
            revoked_at=_parse_datetime(payload.get("revokedAt")),
            revocation_reason=payload.get("revocationReason"),
            subject=str(payload.get("subject", "")),
            group_code=payload.get("groupCode"),
            auto_rotated_from_kid=payload.get("autoRotatedFromKid"),
        )
        summary.key_usage = key_usage
        summary.extended_key_usage = extended_key_usage
        return summary

    def _parse_detail(self, payload: dict[str, Any]) -> CertificateDetail:
        summary = self._parse_summary(payload)
        detail = CertificateDetail(
            kid=summary.kid,
            usage_type=summary.usage_type,
            issued_at=summary.issued_at,
            expires_at=summary.expires_at,
            revoked_at=summary.revoked_at,
            revocation_reason=summary.revocation_reason,
            subject=summary.subject,
            group_code=summary.group_code,
            auto_rotated_from_kid=summary.auto_rotated_from_kid,
            certificate_pem=str(payload.get("certificatePem", "")),
            jwk=payload.get("jwk", {}),
            issuer=str(payload.get("issuer", "")),
            not_before=_parse_datetime(payload.get("notBefore")),
            not_after=_parse_datetime(payload.get("notAfter")),
        )
        detail.key_usage = list(summary.key_usage)
        detail.extended_key_usage = list(summary.extended_key_usage)
        return detail

    def _parse_group(self, payload: dict[str, Any]) -> CertificateGroupData:
        subject = payload.get("subject") or {}
        if not isinstance(subject, dict):
            subject = {}
        return CertificateGroupData(
            group_code=str(payload.get("groupCode", "")),
            display_name=payload.get("displayName"),
            usage_type=_parse_usage(payload.get("usageType")),
            key_type=str(payload.get("keyType", "RSA")),
            key_curve=payload.get("keyCurve"),
            key_size=_parse_optional_int(payload.get("keySize")),
            auto_rotate=bool(payload.get("autoRotate", True)),
            rotation_threshold_days=_parse_optional_int(payload.get("rotationThresholdDays")) or 0,
            subject={str(k): str(v) for k, v in subject.items()},
            created_at=_parse_datetime(payload.get("createdAt")),
            updated_at=_parse_datetime(payload.get("updatedAt")),
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


def _parse_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):  # pragma: no cover - 不正値は想定外
        return None


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
    "CertificateGroupData",
    "IssuedCertificateWithPrivateKey",
    "CertificateSearchResult",
]
