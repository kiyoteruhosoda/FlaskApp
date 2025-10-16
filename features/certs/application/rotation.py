"""証明書自動ローテーションのユースケース"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from features.certs.application.services import (
    CertificateServices,
    default_certificate_services,
)
from features.certs.domain.exceptions import CertificateRotationError
from features.certs.domain.models import CertificateGroup, IssuedCertificate
from features.certs.domain.usage import UsageType
from features.certs.infrastructure.key_utils import (
    SubjectBuilder,
    build_key_usage_extension,
    certificate_to_jwk,
    serialize_private_key,
    serialize_public_key,
    validity_range,
)


class RotationStatus(str, Enum):
    """ローテーション結果のステータス"""

    ROTATED = "rotated"
    SKIPPED = "skipped"
    NOOP = "noop"
    ERROR = "error"


@dataclass(slots=True)
class RotationResult:
    group: CertificateGroup
    status: RotationStatus
    certificate: IssuedCertificate | None = None
    private_key_pem: str | None = None
    public_key_pem: str | None = None
    reason: str | None = None


class AutoRotateCertificatesUseCase:
    """証明書の自動ローテーションを実行するユースケース"""

    def __init__(self, services: CertificateServices | None = None) -> None:
        self._services = services or default_certificate_services

    def execute(self) -> list[RotationResult]:
        groups = self._services.group_store.list_auto_rotating()
        results: list[RotationResult] = []
        now = datetime.utcnow()
        for group in groups:
            if not group.rotation_policy.auto_rotate:
                results.append(
                    RotationResult(
                        group=group,
                        status=RotationStatus.SKIPPED,
                        reason="auto-rotate-disabled",
                    )
                )
                continue

            latest = self._services.issued_store.find_latest_for_group(group.id)
            if not self._should_rotate(group, latest, now):
                results.append(
                    RotationResult(
                        group=group,
                        status=RotationStatus.NOOP,
                        certificate=latest,
                        reason="within-threshold",
                    )
                )
                continue

            active_count = self._services.issued_store.count_active_in_group(group.id)
            if active_count >= 2:
                results.append(
                    RotationResult(
                        group=group,
                        status=RotationStatus.SKIPPED,
                        certificate=latest,
                        reason="active-certificates-limit",
                    )
                )
                continue

            auto_rotated_from = latest.kid if latest else None

            try:
                issued, private_key_pem, public_key_pem = self._issue_certificate(group, latest)
            except CertificateRotationError as exc:
                results.append(
                    RotationResult(
                        group=group,
                        status=RotationStatus.ERROR,
                        reason=str(exc),
                    )
                )
                continue

            issued.auto_rotated_from_kid = auto_rotated_from
            saved = self._services.issued_store.save(issued)
            results.append(
                RotationResult(
                    group=group,
                    status=RotationStatus.ROTATED,
                    certificate=saved,
                    private_key_pem=private_key_pem,
                    public_key_pem=public_key_pem,
                )
            )

        return results

    def _should_rotate(
        self,
        group: CertificateGroup,
        latest: IssuedCertificate | None,
        now: datetime,
    ) -> bool:
        if latest is None:
            return True
        if latest.revoked_at is not None and latest.revoked_at <= now:
            return True
        if latest.expires_at is None:
            return True
        threshold_at = latest.expires_at - timedelta(days=group.rotation_policy.rotation_threshold_days)
        return now >= threshold_at

    def _issue_certificate(
        self,
        group: CertificateGroup,
        latest: IssuedCertificate | None,
    ) -> tuple[IssuedCertificate, str, str]:
        try:
            private_key = self._generate_private_key(group)
        except ValueError as exc:  # noqa: B904
            raise CertificateRotationError(str(exc)) from exc

        subject = SubjectBuilder(group.subject_dict()).build()
        ca_material = self._services.ca_store.get_or_create(group.usage_type)
        validity_days = self._determine_validity_days(group, latest)
        not_before, not_after = validity_range(validity_days)

        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_material.certificate.subject)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_before)
            .not_valid_after(not_after)
        )

        builder = builder.add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        eku = self._extended_key_usage(group.usage_type)
        if eku:
            builder = builder.add_extension(x509.ExtendedKeyUsage(eku), critical=False)

        key_usage_values = self._default_key_usage(group.usage_type)
        key_usage_extension = build_key_usage_extension(key_usage_values)
        if key_usage_extension is not None:
            builder = builder.add_extension(key_usage_extension, critical=True)

        try:
            certificate = builder.sign(private_key=ca_material.private_key, algorithm=hashes.SHA256())
        except Exception as exc:  # noqa: BLE001 - cryptography例外のラップ
            raise CertificateRotationError(str(exc)) from exc

        kid = x509.random_serial_number().to_bytes(20, "big").hex()
        jwk = certificate_to_jwk(certificate, kid, group.usage_type)

        issued = IssuedCertificate(
            kid=kid,
            certificate=certificate,
            usage_type=group.usage_type,
            jwk=jwk,
            issued_at=datetime.utcnow(),
            expires_at=not_after,
            group=group,
            group_id=group.id,
        )

        private_key_pem = serialize_private_key(private_key)
        public_key_pem = serialize_public_key(private_key.public_key())
        return issued, private_key_pem, public_key_pem

    def _determine_validity_days(
        self, group: CertificateGroup, latest: IssuedCertificate | None
    ) -> int:
        if latest and latest.expires_at:
            try:
                not_before = latest.certificate.not_valid_before
                delta = latest.expires_at - not_before
                return max(int(delta.days) or 1, group.rotation_policy.rotation_threshold_days + 1)
            except Exception:  # pragma: no cover - 変換失敗時は既定値
                pass
        return max(group.rotation_policy.rotation_threshold_days * 2, 30)

    def _generate_private_key(
        self, group: CertificateGroup
    ) -> rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey:
        key_type = (group.key_type or "RSA").upper()
        if key_type == "RSA":
            size = group.key_size or 2048
            if size < 2048:
                raise ValueError("RSA鍵は2048bit以上である必要があります")
            return rsa.generate_private_key(public_exponent=65537, key_size=size)
        if key_type == "EC":
            curve_name = (group.key_curve or "P-256").upper()
            curve = self._resolve_curve(curve_name)
            return ec.generate_private_key(curve)
        raise ValueError(f"サポートされていない鍵種別です: {group.key_type}")

    def _resolve_curve(self, curve_name: str) -> ec.EllipticCurve:
        mapping = {
            "P-256": ec.SECP256R1(),
            "P-384": ec.SECP384R1(),
            "P-521": ec.SECP521R1(),
        }
        curve = mapping.get(curve_name.upper())
        if curve is None:
            raise ValueError(f"サポートされていない楕円曲線です: {curve_name}")
        return curve

    def _extended_key_usage(self, usage: UsageType) -> list[x509.ObjectIdentifier] | None:
        if usage == UsageType.SERVER_SIGNING:
            return [x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]
        if usage == UsageType.CLIENT_SIGNING:
            return [x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]
        if usage == UsageType.ENCRYPTION:
            return [x509.oid.ExtendedKeyUsageOID.EMAIL_PROTECTION]
        return None

    def _default_key_usage(self, usage: UsageType) -> list[str]:
        if usage == UsageType.ENCRYPTION:
            return ["digitalSignature", "keyEncipherment"]
        return ["digitalSignature"]


__all__ = [
    "AutoRotateCertificatesUseCase",
    "RotationResult",
    "RotationStatus",
]
