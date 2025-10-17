from datetime import datetime
from unittest.mock import MagicMock

from features.certs.application.rotation import AutoRotateCertificatesUseCase
from features.certs.domain.models import CertificateGroup, IssuedCertificate, RotationPolicy
from features.certs.domain.usage import UsageType


def test_auto_rotation_skips_non_expiring_signing_keys():
    use_case = AutoRotateCertificatesUseCase(services=MagicMock())

    group = CertificateGroup(
        id=1,
        group_code="signing-group",
        usage_type=UsageType.SERVER_SIGNING,
        subject={},
        key_type="RSA",
        rotation_policy=RotationPolicy(auto_rotate=True, rotation_threshold_days=30),
    )

    issued = IssuedCertificate(
        kid="kid-1",
        usage_type=UsageType.SERVER_SIGNING,
        jwk={"kty": "RSA"},
        issued_at=datetime.utcnow(),
        certificate=None,
        certificate_pem="",
        expires_at=None,
        group=group,
        group_id=group.id,
    )

    assert use_case._should_rotate(group, issued, datetime.utcnow()) is False
