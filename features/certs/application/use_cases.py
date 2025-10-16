"""証明書機能のユースケース"""
from __future__ import annotations

import uuid
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from features.certs.domain.exceptions import (
    CertificateGroupNotFoundError,
    CertificateSigningError,
    CertificateValidationError,
    KeyGenerationError,
)
from features.certs.domain.models import GeneratedKeyMaterial, IssuedCertificate
from features.certs.domain.usage import UsageType
from features.certs.application.services import (
    CertificateServices,
    default_certificate_services,
)
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


class GenerateCertificateMaterialUseCase:
    """鍵ペア生成ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or default_certificate_services

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
        self._services = services or default_certificate_services

    def execute(self, payload: SignCertificateInput) -> SignCertificateOutput:
        if not payload.csr_pem:
            raise CertificateValidationError("csrPemは必須です")

        csr = csr_from_pem(payload.csr_pem)
        if not csr.is_signature_valid:
            raise CertificateValidationError("CSRの署名が不正です")

        group = None
        if payload.group_code:
            try:
                group = self._services.group_store.get_by_code(payload.group_code)
            except CertificateGroupNotFoundError:
                raise CertificateValidationError(
                    f"指定されたグループが存在しません: {payload.group_code}"
                ) from None
            if group.usage_type != payload.usage_type:
                raise CertificateValidationError("グループの用途とusageTypeが一致しません")

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

        expires_at = not_after

        issued = IssuedCertificate(
            kid=kid,
            certificate=certificate,
            usage_type=payload.usage_type,
            jwk=jwk,
            issued_at=datetime.utcnow(),
            expires_at=expires_at,
            group=group,
            group_id=group.id if group else None,
        )
        self._services.issued_store.save(issued)

        return SignCertificateOutput(
            certificate_pem=certificate.public_bytes(serialization.Encoding.PEM).decode("utf-8"),
            kid=kid,
            jwk=jwk,
            usage_type=payload.usage_type,
            group_code=group.group_code if group else None,
        )


class ListJwksUseCase:
    """JWKS取得ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or default_certificate_services

    def execute(self, group_code: str) -> dict:
        self._services.group_store.get_by_code(group_code)
        keys = self._services.issued_store.list_jwks_for_group(group_code)
        return {"keys": keys}


class ListIssuedCertificatesUseCase:
    """発行済み証明書一覧取得ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or default_certificate_services

    def execute(
        self,
        usage_type: UsageType | None = None,
        *,
        group_code: str | None = None,
    ) -> list[IssuedCertificate]:
        return self._services.issued_store.list(usage_type, group_code=group_code)


class GetIssuedCertificateUseCase:
    """証明書詳細取得ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or default_certificate_services

    def execute(self, kid: str) -> IssuedCertificate:
        return self._services.issued_store.get(kid)


class RevokeCertificateUseCase:
    """証明書失効ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or default_certificate_services

    def execute(self, kid: str, reason: str | None = None) -> IssuedCertificate:
        return self._services.issued_store.revoke(kid, reason)
