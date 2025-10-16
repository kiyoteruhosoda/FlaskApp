"""証明書機能で利用するドメインモデル"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

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
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
