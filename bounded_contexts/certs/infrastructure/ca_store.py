"""CA鍵の管理ロジック"""
from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from bounded_contexts.certs.domain.models import CAKeyMaterial
from bounded_contexts.certs.domain.usage import UsageType


class CAKeyStore:
    """用途別のCA鍵をオンメモリで管理"""

    def __init__(self) -> None:
        self._materials: dict[UsageType, CAKeyMaterial] = {}
        self._lock = Lock()

    def get_or_create(self, usage: UsageType) -> CAKeyMaterial:
        """指定用途のCA鍵を取得、未生成なら作成"""

        with self._lock:
            material = self._materials.get(usage)
            if material is not None:
                return material

            private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
            subject = x509.Name(
                [
                    x509.NameAttribute(NameOID.COUNTRY_NAME, "JP"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "CertVault"),
                    x509.NameAttribute(NameOID.COMMON_NAME, f"CertVault {usage.value} CA"),
                ]
            )
            now = datetime.utcnow()
            certificate = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(subject)
                .public_key(private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1))
                .not_valid_after(now + timedelta(days=3650))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .sign(private_key, hashes.SHA256())
            )

            material = CAKeyMaterial(private_key=private_key, certificate=certificate)
            self._materials[usage] = material
            return material

    def export_pem(self, usage: UsageType) -> tuple[str, str]:
        """CA秘密鍵と証明書をPEM文字列で返す"""

        material = self.get_or_create(usage)
        private_pem = material.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        cert_pem = material.certificate.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        return private_pem, cert_pem
