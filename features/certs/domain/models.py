"""証明書機能で利用するドメインモデル"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa

from .usage import UsageType


@dataclass(slots=True)
class GeneratedKeyMaterial:
    """生成済みの鍵ペアやCSRを格納するモデル"""

    private_key_pem: str
    public_key_pem: str
    csr_pem: str | None
    thumbprint: str
    usage_type: UsageType


@dataclass(slots=True)
class CAKeyMaterial:
    """CA鍵に関する情報"""

    private_key: rsa.RSAPrivateKey
    certificate: x509.Certificate


@dataclass(slots=True)
class IssuedCertificate:
    """署名済み証明書の保持モデル"""

    kid: str
    certificate: x509.Certificate
    usage_type: UsageType
    jwk: dict
    issued_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    group_id: int | None = None
    group: "CertificateGroup" | None = None
    auto_rotated_from_kid: str | None = None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


@dataclass(slots=True)
class RotationPolicy:
    """証明書ローテーションのポリシー設定"""

    auto_rotate: bool
    rotation_threshold_days: int


@dataclass(slots=True)
class CertificateGroup:
    """証明書グループの定義"""

    id: int
    group_code: str
    usage_type: UsageType
    subject: dict[str, str]
    key_type: str
    rotation_policy: RotationPolicy
    display_name: str | None = None
    key_curve: str | None = None
    key_size: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def subject_dict(self) -> dict[str, Any]:
        """テンプレートsubjectを辞書で返す"""

        return dict(self.subject)
