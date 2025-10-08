import pytest
from unittest.mock import create_autospec

from domain.user import (
    EmailAlreadyRegisteredError,
    RegistrationIntent,
    User,
    UserRegistrationService,
)
from domain.user.repository import UserRepository


def _build_service(repo=None) -> UserRegistrationService:
    repository = repo or create_autospec(UserRepository, instance=True)
    return UserRegistrationService(repository)


def test_register_new_user_sets_password_and_roles():
    repo = create_autospec(UserRepository, instance=True)
    repo.get_by_email.return_value = None
    repo.add.side_effect = lambda user, roles: user

    service = _build_service(repo)
    intent = RegistrationIntent.create(
        email="new@example.com",
        raw_password="secret",
        roles=["guest", "editor"],
        totp_secret="TOTP",
        is_active=True,
    )

    user = service.register(intent)

    assert user.email == "new@example.com"
    assert user.is_active is True
    assert user.totp_secret == "TOTP"
    assert user.check_password("secret")
    repo.add.assert_called_once()
    _, roles = repo.add.call_args[0]
    assert roles == ["guest", "editor"]


def test_register_raises_when_active_user_exists():
    existing_user = User(email="dup@example.com", is_active=True)
    existing_user.password_hash = "existing"

    repo = create_autospec(UserRepository, instance=True)
    repo.get_by_email.return_value = existing_user

    service = _build_service(repo)
    intent = RegistrationIntent.create(
        email="dup@example.com",
        raw_password="secret",
    )

    with pytest.raises(EmailAlreadyRegisteredError):
        service.register(intent)
    repo.delete.assert_not_called()
    repo.add.assert_not_called()


def test_register_replaces_inactive_user():
    existing_user = User(email="inactive@example.com", is_active=False)
    existing_user.password_hash = "existing"

    repo = create_autospec(UserRepository, instance=True)
    repo.get_by_email.return_value = existing_user
    repo.add.side_effect = lambda user, roles: user

    service = _build_service(repo)
    intent = RegistrationIntent.create(
        email="inactive@example.com",
        raw_password="new-secret",
        roles=["guest"],
    )

    user = service.register(intent)

    repo.delete.assert_called_once_with(existing_user)
    assert user.email == "inactive@example.com"
    assert user.is_active is True
    assert user.check_password("new-secret")


def test_activate_with_totp_updates_user():
    user = User(email="pending@example.com", is_active=False)
    user.password_hash = "hashed"

    repo = create_autospec(UserRepository, instance=True)
    repo.update.side_effect = lambda updated_user: updated_user

    service = _build_service(repo)

    updated_user = service.activate_with_totp(user, "NEWTOTP")

    assert updated_user.is_active is True
    assert updated_user.totp_secret == "NEWTOTP"
    repo.update.assert_called_once_with(user)
