"""証明書機能で利用する共通サービス定義"""
from __future__ import annotations

from dataclasses import dataclass

from features.certs.infrastructure.ca_store import CAKeyStore
from features.certs.infrastructure.group_store import CertificateGroupStore
from features.certs.infrastructure.issued_store import IssuedCertificateStore


@dataclass(slots=True)
class CertificateServices:
    ca_store: CAKeyStore
    issued_store: IssuedCertificateStore
    group_store: CertificateGroupStore


default_certificate_services = CertificateServices(
    ca_store=CAKeyStore(),
    issued_store=IssuedCertificateStore(),
    group_store=CertificateGroupStore(),
)


__all__ = ["CertificateServices", "default_certificate_services"]
