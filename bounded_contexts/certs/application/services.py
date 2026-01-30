"""証明書機能で利用する共通サービス定義"""
from __future__ import annotations

from dataclasses import dataclass

from bounded_contexts.certs.infrastructure.ca_store import CAKeyStore
from bounded_contexts.certs.infrastructure.event_store import CertificateEventStore
from bounded_contexts.certs.infrastructure.group_store import CertificateGroupStore
from bounded_contexts.certs.infrastructure.private_key_store import CertificatePrivateKeyStore
from bounded_contexts.certs.infrastructure.issued_store import IssuedCertificateStore


@dataclass(slots=True)
class CertificateServices:
    ca_store: CAKeyStore
    issued_store: IssuedCertificateStore
    group_store: CertificateGroupStore
    event_store: CertificateEventStore
    private_key_store: CertificatePrivateKeyStore


default_certificate_services = CertificateServices(
    ca_store=CAKeyStore(),
    issued_store=IssuedCertificateStore(),
    group_store=CertificateGroupStore(),
    event_store=CertificateEventStore(),
    private_key_store=CertificatePrivateKeyStore(),
)


__all__ = ["CertificateServices", "default_certificate_services"]
