"""発行済み証明書の保存"""
from __future__ import annotations

from datetime import datetime
from threading import Lock

from features.certs.domain.models import IssuedCertificate
from features.certs.domain.usage import UsageType


class IssuedCertificateStore:
    """簡易的なオンメモリストア"""

    def __init__(self) -> None:
        self._store: dict[str, IssuedCertificate] = {}
        self._lock = Lock()

    def add(self, cert: IssuedCertificate) -> None:
        with self._lock:
            self._store[cert.kid] = cert

    def list_by_usage(self, usage: UsageType) -> list[IssuedCertificate]:
        with self._lock:
            return [cert for cert in self._store.values() if cert.usage_type == usage]

    def get(self, kid: str) -> IssuedCertificate | None:
        with self._lock:
            return self._store.get(kid)

    def revoke(self, kid: str) -> None:
        with self._lock:
            self._store.pop(kid, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
