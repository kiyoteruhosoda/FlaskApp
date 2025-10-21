import pytest

from core.models.user import User
from shared.application.authenticated_principal import AuthenticatedPrincipal
from webapp.extensions import db
from webapp.services.token_service import TokenService


@pytest.mark.usefixtures("app_context")
def test_revoke_refresh_token_clears_hash():
    user = User(email="logout-test@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    _, refresh_token = TokenService.generate_token_pair(user)

    assert user.refresh_token_hash is not None
    assert user.check_refresh_token(refresh_token)

    TokenService.revoke_refresh_token(user)
    db.session.refresh(user)

    assert user.refresh_token_hash is None
    assert not user.check_refresh_token(refresh_token)


@pytest.mark.usefixtures("app_context")
def test_revoke_refresh_token_accepts_principal():
    user = User(email="logout-principal@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    _, refresh_token = TokenService.generate_token_pair(user)

    principal = AuthenticatedPrincipal(
        subject_type="individual",
        subject_id=user.id,
        identifier=f"i+{user.id}",
        scope=frozenset(),
        display_name=user.email,
    )

    TokenService.revoke_refresh_token(principal)
    db.session.refresh(user)

    assert user.refresh_token_hash is None
    assert not user.check_refresh_token(refresh_token)
