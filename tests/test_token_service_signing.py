import jwt
import pytest

from datetime import datetime, timedelta, timezone
from flask import current_app

from core.models.user import User
from shared.application.authenticated_principal import AuthenticatedPrincipal
from core.settings import settings

from features.certs.application.use_cases import IssueCertificateForGroupUseCase
from features.certs.domain.usage import UsageType
from features.certs.infrastructure.models import CertificateGroupEntity, IssuedCertificateEntity
from webapp.extensions import db
from webapp.services.access_token_signing import AccessTokenSigningError
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
    SystemSettingService.update_access_token_signing_setting("server_signing", group_code=group.group_code)

    token = TokenService.generate_access_token(user)
    header = jwt.get_unverified_header(token)
    assert header.get("alg") == issued.jwk.get("alg")
    assert header.get("kid") == issued.kid

    claims = jwt.decode(
        token,
        options={
            "verify_signature": False,
            "verify_exp": False,
            "verify_aud": False,
            "verify_iss": False,
        },
        algorithms=[header.get("alg")],
    )
    assert claims["iss"] == settings.access_token_issuer
    assert claims["aud"] == settings.access_token_audience
    assert claims["sub"] == f"i+{user.id}"
    assert claims["subject_type"] == "individual"
    assert "email" not in claims

    verification = TokenService.verify_access_token(token)
    assert isinstance(verification, AuthenticatedPrincipal)
    assert verification.subject_type == "individual"
    assert verification.id == user.id
    assert verification.scope == frozenset()


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
    SystemSettingService.update_access_token_signing_setting("server_signing", group_code=group.group_code)

    verification = TokenService.verify_access_token(legacy_token)
    assert isinstance(verification, AuthenticatedPrincipal)
    assert verification.subject_type == "individual"
    assert verification.id == user.id
    assert verification.scope == frozenset()


@pytest.mark.usefixtures("app_context")
def test_latest_certificate_is_used_for_group():
    user = User(email="rotate@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    group = CertificateGroupEntity(
        group_code="server-signing-rotate",
        display_name="Server Signing Rotate",
        auto_rotate=False,
        rotation_threshold_days=30,
        key_type="RSA",
        key_curve=None,
        key_size=2048,
        subject={"CN": "Server Signing Rotate"},
        usage_type=UsageType.SERVER_SIGNING.value,
    )
    db.session.add(group)
    db.session.commit()

    first = IssueCertificateForGroupUseCase().execute(group.group_code)
    SystemSettingService.update_access_token_signing_setting("server_signing", group_code=group.group_code)

    first_token = TokenService.generate_access_token(user)
    first_header = jwt.get_unverified_header(first_token)
    assert first_header.get("kid") == first.kid

    second = IssueCertificateForGroupUseCase().execute(group.group_code)

    second_token = TokenService.generate_access_token(user)
    second_header = jwt.get_unverified_header(second_token)
    assert second_header.get("kid") == second.kid
    assert second_header.get("kid") != first_header.get("kid")

    assert isinstance(TokenService.verify_access_token(first_token), AuthenticatedPrincipal)
    assert isinstance(TokenService.verify_access_token(second_token), AuthenticatedPrincipal)


@pytest.mark.usefixtures("app_context")
def test_verify_access_token_rejects_invalid_audience():
    user = User(email="aud-check@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    token = TokenService.generate_access_token(user)

    SystemSettingService.upsert_application_config({"ACCESS_TOKEN_AUDIENCE": "unexpected"})
    current_app.config["ACCESS_TOKEN_AUDIENCE"] = "unexpected"

    assert TokenService.verify_access_token(token) is None


@pytest.mark.usefixtures("app_context")
def test_revoked_certificate_configuration_surfaces_error():
    user = User(email="revoked@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    group = CertificateGroupEntity(
        group_code="server-signing-revoked",
        display_name="Server Signing Revoked",
        auto_rotate=False,
        rotation_threshold_days=30,
        key_type="RSA",
        key_curve=None,
        key_size=2048,
        subject={"CN": "Server Signing Revoked"},
        usage_type=UsageType.SERVER_SIGNING.value,
    )
    db.session.add(group)
    db.session.commit()

    issued = IssueCertificateForGroupUseCase().execute(group.group_code)
    SystemSettingService.update_access_token_signing_setting("server_signing", group_code=group.group_code)

    certificate_entity = IssuedCertificateEntity.query.get(issued.kid)
    certificate_entity.revoked_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.session.add(certificate_entity)
    db.session.commit()

    signing_setting = SystemSettingService.get_access_token_signing_setting()
    assert signing_setting.is_server_signing

    with pytest.raises(AccessTokenSigningError):
        TokenService.generate_access_token(user)
