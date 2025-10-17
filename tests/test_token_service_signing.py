import jwt
import pytest

from core.models.user import User
from features.certs.application.use_cases import IssueCertificateForGroupUseCase
from features.certs.domain.usage import UsageType
from features.certs.infrastructure.models import CertificateGroupEntity
from webapp.extensions import db
from webapp.services.system_setting_service import SystemSettingService
from webapp.services.token_service import TokenService


@pytest.mark.usefixtures("app_context")
def test_generate_access_token_with_server_signing():
    user = User(email="server-sign@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    group = CertificateGroupEntity(
        group_code="server-signing",
        display_name="Server Signing",
        auto_rotate=False,
        rotation_threshold_days=30,
        key_type="RSA",
        key_curve=None,
        key_size=2048,
        subject={"CN": "Server Signing"},
        usage_type=UsageType.SERVER_SIGNING.value,
    )
    db.session.add(group)
    db.session.commit()

    issued = IssueCertificateForGroupUseCase().execute(group.group_code)
    SystemSettingService.update_access_token_signing_setting("server_signing", kid=issued.kid)

    token = TokenService.generate_access_token(user)
    header = jwt.get_unverified_header(token)
    assert header.get("alg") == issued.jwk.get("alg")
    assert header.get("kid") == issued.kid

    verification = TokenService.verify_access_token(token)
    assert verification is not None
    verified_user, scopes = verification
    assert verified_user.id == user.id
    assert scopes == set()


@pytest.mark.usefixtures("app_context")
def test_verify_builtin_token_after_switch_to_server_signing():
    user = User(email="legacy@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    legacy_token = TokenService.generate_access_token(user)

    group = CertificateGroupEntity(
        group_code="server-signing-legacy",
        display_name="Server Signing Legacy",
        auto_rotate=False,
        rotation_threshold_days=30,
        key_type="RSA",
        key_curve=None,
        key_size=2048,
        subject={"CN": "Server Signing Legacy"},
        usage_type=UsageType.SERVER_SIGNING.value,
    )
    db.session.add(group)
    db.session.commit()

    issued = IssueCertificateForGroupUseCase().execute(group.group_code)
    SystemSettingService.update_access_token_signing_setting("server_signing", kid=issued.kid)

    verification = TokenService.verify_access_token(legacy_token)
    assert verification is not None
    verified_user, scopes = verification
    assert verified_user.id == user.id
    assert scopes == set()
