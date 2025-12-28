"""AuthService のユニットテスト."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional

import pytest

from shared.application.auth_service import AuthService
from shared.domain.user.entities import User
from shared.domain.user.repository import UserRepository
from shared.domain.user.services import UserRegistrationService


@dataclass
class InMemoryUserRepository(UserRepository):
    """シンプルなメモリ内ユーザーリポジトリ（テスト用）."""

    _users: Dict[str, User] = field(default_factory=dict)

    def get_by_email(self, email: str) -> Optional[User]:
        return self._users.get(email)

    def add(self, user: User, role_names: Iterable[str]) -> User:
        # 役割はアプリケーション層で処理されるためここでは保持しない
        self._users[user.email] = user
        return user

    def update(self, user: User) -> User:
        self._users[user.email] = user
        return user

    def delete(self, user: User) -> None:
        self._users.pop(user.email, None)

    def get_model(self, user: User):  # pragma: no cover - テストでは不要
        return None


@pytest.fixture
def repository() -> InMemoryUserRepository:
    return InMemoryUserRepository()


@pytest.fixture
def service(repository: InMemoryUserRepository) -> AuthService:
    return AuthService(repo=repository, registrar=UserRegistrationService(repository))


def test_register_creates_active_user_with_totp(service: AuthService, repository: InMemoryUserRepository) -> None:
    service.register("user@example.com", "password", totp_secret="secret", roles=["admin"])

    stored = repository.get_by_email("user@example.com")
    assert stored is not None
    assert stored.is_active is True
    assert stored.totp_secret == "secret"
    assert stored.check_password("password") is True
    assert stored.check_password("bad") is False


def test_register_with_pending_totp_creates_inactive_user(service: AuthService, repository: InMemoryUserRepository) -> None:
    user = service.register_with_pending_totp("pending@example.com", "password")

    stored = repository.get_by_email("pending@example.com")
    assert stored is not None
    assert stored.is_active is False
    assert stored.totp_secret is None
    assert stored.check_password("password")

    activated = service.activate_user_with_totp(user, "totp-secret")
    assert activated.is_active is True
    assert activated.totp_secret == "totp-secret"
