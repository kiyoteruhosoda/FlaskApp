"""証明書機能のDTO"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from features.certs.domain.models import GeneratedKeyMaterial
from features.certs.domain.usage import UsageType


@dataclass(slots=True)
class GenerateCertificateMaterialInput:
    subject: dict[str, str] | None = None
    key_type: str = "RSA"
    key_bits: int = 2048
    make_csr: bool = True
    usage_type: UsageType = UsageType.SERVER_SIGNING
    key_usage: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GenerateCertificateMaterialOutput:
    material: GeneratedKeyMaterial


@dataclass(slots=True)
class SignCertificateInput:
    csr_pem: str
    usage_type: UsageType
    days: int = 365
    is_ca: bool = False
    key_usage: list[str] = field(default_factory=list)
    group_code: str | None = None


@dataclass(slots=True)
class SignCertificateOutput:
    certificate_pem: str
    kid: str
    jwk: dict[str, Any]
    usage_type: UsageType
    group_code: str | None = None


@dataclass(slots=True, kw_only=True)
class CertificateGroupInput:
    group_code: str
    display_name: str | None
    usage_type: UsageType
    key_type: str
    key_curve: str | None
    key_size: int | None
    auto_rotate: bool
    rotation_threshold_days: int
    subject: dict[str, str]
    key_usage: tuple[str, ...] | None = None


@dataclass(slots=True, kw_only=True)
class CertificateGroupUpdateInput(CertificateGroupInput):
    id: int


@dataclass(slots=True)
class IssueCertificateForGroupOutput:
    kid: str
    certificate_pem: str
    private_key_pem: str
    jwk: dict[str, Any]
    usage_type: UsageType
    group_code: str


@dataclass(slots=True)
class SignGroupPayloadInput:
    group_code: str
    payload: bytes
    kid: str
    hash_algorithm: str = "SHA256"


@dataclass(slots=True)
class SignGroupPayloadOutput:
    kid: str
    signature: bytes
    hash_algorithm: str
    algorithm: str


@dataclass(slots=True)
class CertificateSearchFilters:
    limit: int = 50
    offset: int = 0
    kid: str | None = None
    group_code: str | None = None
    usage_type: UsageType | None = None
    subject_contains: str | None = None
    issued_from: datetime | None = None
    issued_to: datetime | None = None
    expires_from: datetime | None = None
    expires_to: datetime | None = None
    revoked: bool | None = None


@dataclass(slots=True)
class CertificateSearchResult:
    total: int
    certificates: list[Any]
