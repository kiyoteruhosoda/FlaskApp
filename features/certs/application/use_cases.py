"""証明書機能のユースケース"""
from __future__ import annotations

import uuid
from datetime import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from dataclasses import replace

from features.certs.domain.exceptions import (
    CertificateGroupConflictError,
    CertificateGroupNotFoundError,
    CertificateSigningError,
    CertificateValidationError,
    KeyGenerationError,
)
from features.certs.domain.models import (
    CertificateGroup,
    GeneratedKeyMaterial,
    IssuedCertificate,
    RotationPolicy,
)
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
    CertificateGroupInput,
    CertificateSearchFilters,
    CertificateSearchResult,
    GenerateCertificateMaterialInput,
    GenerateCertificateMaterialOutput,
    IssueCertificateForGroupOutput,
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

    def execute(
        self,
        payload: SignCertificateInput,
        *,
        actor: str | None = None,
    ) -> SignCertificateOutput:
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
        saved = self._services.issued_store.save(issued)

        if saved.group:
            # 証明書変更時にJWKSを再構築
            ListJwksUseCase(self._services).execute(saved.group.group_code)

        if actor:
            self._services.event_store.record(
                actor=actor,
                action="issue_certificate",
                target_kid=saved.kid,
                target_group_code=saved.group.group_code if saved.group else None,
            )

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

    def execute(
        self,
        kid: str,
        reason: str | None = None,
        *,
        actor: str | None = None,
    ) -> IssuedCertificate:
        revoked = self._services.issued_store.revoke(kid, reason)
        if revoked.group:
            ListJwksUseCase(self._services).execute(revoked.group.group_code)
        if actor:
            self._services.event_store.record(
                actor=actor,
                action="revoke_certificate",
                target_kid=revoked.kid,
                target_group_code=revoked.group.group_code if revoked.group else None,
                reason=reason,
            )
        return revoked


class ListCertificateGroupsUseCase:
    """証明書グループ一覧取得ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or default_certificate_services

    def execute(self) -> list[CertificateGroup]:
        return self._services.group_store.list_all()


class GetCertificateGroupUseCase:
    """証明書グループ詳細取得ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or default_certificate_services

    def execute(self, group_code: str) -> CertificateGroup:
        return self._services.group_store.get_by_code(group_code)


class CreateCertificateGroupUseCase:
    """証明書グループ登録ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or default_certificate_services

    def execute(
        self,
        payload: CertificateGroupInput,
        *,
        actor: str | None = None,
    ) -> CertificateGroup:
        rotation_policy = RotationPolicy(
            auto_rotate=payload.auto_rotate,
            rotation_threshold_days=payload.rotation_threshold_days,
        )
        group = CertificateGroup(
            id=0,
            group_code=payload.group_code,
            display_name=payload.display_name,
            rotation_policy=rotation_policy,
            usage_type=payload.usage_type,
            key_type=payload.key_type,
            key_curve=payload.key_curve,
            key_size=payload.key_size,
            subject=payload.subject,
        )
        created = self._services.group_store.create(group)
        if actor:
            self._services.event_store.record(
                actor=actor,
                action="create_group",
                target_group_code=created.group_code,
            )
        return created


class UpdateCertificateGroupUseCase:
    """証明書グループ更新ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or default_certificate_services

    def execute(
        self,
        payload: CertificateGroupInput,
        *,
        actor: str | None = None,
    ) -> CertificateGroup:
        existing = self._services.group_store.get_by_code(payload.group_code)
        rotation_policy = RotationPolicy(
            auto_rotate=payload.auto_rotate,
            rotation_threshold_days=payload.rotation_threshold_days,
        )
        updated_group = replace(
            existing,
            display_name=payload.display_name,
            rotation_policy=rotation_policy,
            usage_type=payload.usage_type,
            key_type=payload.key_type,
            key_curve=payload.key_curve,
            key_size=payload.key_size,
            subject=payload.subject,
        )
        saved = self._services.group_store.update(updated_group)
        if actor:
            self._services.event_store.record(
                actor=actor,
                action="update_group",
                target_group_code=saved.group_code,
            )
        return saved


class DeleteCertificateGroupUseCase:
    """証明書グループ削除ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or default_certificate_services

    def execute(self, group_code: str, *, actor: str | None = None) -> None:
        group = self._services.group_store.get_by_code(group_code)
        try:
            self._services.group_store.delete(group_code)
        except CertificateGroupConflictError:
            raise
        if actor:
            self._services.event_store.record(
                actor=actor,
                action="delete_group",
                target_group_code=group.group_code,
            )


class IssueCertificateForGroupUseCase:
    """管理グループに基づき証明書を発行するユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or default_certificate_services

    def execute(
        self,
        group_code: str,
        *,
        actor: str | None = None,
        subject_overrides: dict[str, str] | None = None,
        valid_days: int | None = None,
        key_usage: list[str] | None = None,
    ) -> IssueCertificateForGroupOutput:
        group = self._services.group_store.get_by_code(group_code)
        try:
            private_key = generate_private_key(group.key_type, group.key_size or 2048)
        except KeyGenerationError:
            raise
        except Exception as exc:  # noqa: BLE001 - cryptography由来の例外をラップ
            raise KeyGenerationError(str(exc)) from exc

        subject_dict = group.subject_dict()
        if subject_overrides:
            subject_dict.update(subject_overrides)
        subject = SubjectBuilder(subject_dict).build()
        csr = build_csr(private_key, subject, group.usage_type, key_usage or [])
        csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")

        default_days = max(group.rotation_policy.rotation_threshold_days * 2, 1)
        days = valid_days if valid_days and valid_days > 0 else default_days
        sign_input = SignCertificateInput(
            csr_pem=csr_pem,
            usage_type=group.usage_type,
            days=days,
            is_ca=False,
            key_usage=key_usage or [],
            group_code=group.group_code,
        )
        sign_result = SignCertificateUseCase(self._services).execute(
            sign_input,
            actor=actor,
        )

        return IssueCertificateForGroupOutput(
            kid=sign_result.kid,
            certificate_pem=sign_result.certificate_pem,
            private_key_pem=serialize_private_key(private_key),
            jwk=sign_result.jwk,
            usage_type=group.usage_type,
            group_code=group.group_code,
        )


class SearchCertificatesUseCase:
    """証明書検索ユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or default_certificate_services

    def execute(self, filters: CertificateSearchFilters) -> CertificateSearchResult:
        certificates, total = self._services.issued_store.search(filters)
        return CertificateSearchResult(total=total, certificates=certificates)
