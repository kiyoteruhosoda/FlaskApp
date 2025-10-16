"""証明書機能のDTO"""
from __future__ import annotations

from dataclasses import dataclass, field
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
