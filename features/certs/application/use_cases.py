"""証明書機能のユースケース"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from features.certs.domain.exceptions import (
    CertificateNotFoundError,
    CertificateSigningError,
    CertificateValidationError,
    KeyGenerationError,
)
from features.certs.domain.models import GeneratedKeyMaterial, IssuedCertificate
from features.certs.domain.usage import UsageType
from features.certs.infrastructure.ca_store import CAKeyStore
from features.certs.infrastructure.issued_store import IssuedCertificateStore
from features.certs.infrastructure.key_utils import (
    SubjectBuilder,
    build_csr,
    build_key_usage_extension,
    certificate_to_jwk,
    compute_thumbprint,
    csr_from_pem,
    generate_private_key,
    serialize_private_key,
    serialize_public_key,
    validity_range,
)

from .dto import (
    GenerateCertificateMaterialInput,
    GenerateCertificateMaterialOutput,
    SignCertificateInput,
    SignCertificateOutput,
)


@dataclass(slots=True)
class CertificateServices:
    ca_store: CAKeyStore
    issued_store: IssuedCertificateStore


_default_services = CertificateServices(ca_store=CAKeyStore(), issued_store=IssuedCertificateStore())


class GenerateCertificateMaterialUseCase:
    """鍵ペア生成ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or _default_services

    def execute(self, payload: GenerateCertificateMaterialInput) -> GenerateCertificateMaterialOutput:
        try:
            private_key = generate_private_key(payload.key_type, payload.key_bits)
        except KeyGenerationError:
            raise
        except Exception as exc:  # noqa: BLE001 - cryptographyからの例外のラップ
            raise KeyGenerationError(str(exc)) from exc

        subject = SubjectBuilder(payload.subject).build()

        csr_pem = None
        if payload.make_csr:
            csr = build_csr(private_key, subject, payload.usage_type, payload.key_usage)
            csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")

        material = GeneratedKeyMaterial(
            private_key_pem=serialize_private_key(private_key),
            public_key_pem=serialize_public_key(private_key.public_key()),
            csr_pem=csr_pem,
            thumbprint=compute_thumbprint(private_key.public_key()),
            usage_type=payload.usage_type,
        )
        return GenerateCertificateMaterialOutput(material=material)


class SignCertificateUseCase:
    """CSR署名ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or _default_services

    def execute(self, payload: SignCertificateInput) -> SignCertificateOutput:
        if not payload.csr_pem:
            raise CertificateValidationError("csrPemは必須です")

        csr = csr_from_pem(payload.csr_pem)
        if not csr.is_signature_valid:
            raise CertificateValidationError("CSRの署名が不正です")

        ca_material = self._services.ca_store.get_or_create(payload.usage_type)
        not_before, not_after = validity_range(payload.days)

        builder = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(ca_material.certificate.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
        )

        is_ca = payload.is_ca
        builder = builder.add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)

        key_usage_extension = build_key_usage_extension(payload.key_usage)
        if key_usage_extension is not None:
            builder = builder.add_extension(key_usage_extension, critical=True)

        eku = None
        if payload.usage_type == UsageType.SERVER_SIGNING:
            eku = x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH])
        elif payload.usage_type == UsageType.CLIENT_SIGNING:
            eku = x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH])
        elif payload.usage_type == UsageType.ENCRYPTION:
            eku = x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.EMAIL_PROTECTION])
        if eku:
            builder = builder.add_extension(eku, critical=False)

        try:
            certificate = builder.sign(private_key=ca_material.private_key, algorithm=hashes.SHA256())
        except Exception as exc:  # noqa: BLE001
            raise CertificateSigningError(str(exc)) from exc

        kid = uuid.uuid4().hex
        jwk = certificate_to_jwk(certificate, kid, payload.usage_type)

        issued = IssuedCertificate(
            kid=kid,
            certificate=certificate,
            usage_type=payload.usage_type,
            jwk=jwk,
            issued_at=datetime.utcnow(),
        )
        self._services.issued_store.add(issued)

        return SignCertificateOutput(
            certificate_pem=certificate.public_bytes(serialization.Encoding.PEM).decode("utf-8"),
            kid=kid,
            jwk=jwk,
            usage_type=payload.usage_type,
        )


class ListJwksUseCase:
    """JWKS取得ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or _default_services

    def execute(self, usage_type: UsageType) -> dict:
        certificates = self._services.issued_store.list_by_usage(usage_type)
        keys = [cert.jwk for cert in certificates if not cert.is_revoked]
        return {"keys": keys}


class ListIssuedCertificatesUseCase:
    """発行済み証明書一覧取得ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or _default_services

    def execute(self, usage_type: UsageType | None = None) -> list[IssuedCertificate]:
        store = self._services.issued_store
        if usage_type is None:
            return store.list_all()
        return store.list_by_usage(usage_type)


class GetIssuedCertificateUseCase:
    """証明書詳細取得ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or _default_services

    def execute(self, kid: str) -> IssuedCertificate:
        cert = self._services.issued_store.get(kid)
        if cert is None:
            raise CertificateNotFoundError("指定された証明書が見つかりません")
        return cert


class RevokeCertificateUseCase:
    """証明書失効ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or _default_services

    def execute(self, kid: str, reason: str | None = None) -> IssuedCertificate:
        cert = self._services.issued_store.revoke(kid, reason)
        if cert is None:
            raise CertificateNotFoundError("指定された証明書が見つかりません")
        return cert
