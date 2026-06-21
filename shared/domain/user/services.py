"""ユーザー登録に関するドメインサービス。"""

from __future__ import annotations

from dataclasses import dataclass

from .entities import User
from .exceptions import EmailAlreadyRegisteredError
from .repository import UserRepository
from .value_objects import RegistrationIntent


@dataclass
class UserRegistrationService:
    """ユーザーの登録ポリシーを担うドメインサービス。"""

    repository: UserRepository

    def register(self, intent: RegistrationIntent) -> User:
        existing_user = self.repository.get_by_email(intent.email)
        if existing_user is not None:
            if existing_user.is_active:
                raise EmailAlreadyRegisteredError(intent.email)
            self.repository.delete(existing_user)

        user = self._build_user(intent)
        return self.repository.add(user, list(intent.roles))

    def activate_with_totp(self, user: User, totp_secret: str) -> User:
        user.activate(totp_secret=totp_secret)
        return self.repository.update(user)

    def _build_user(self, intent: RegistrationIntent) -> User:
        user = User(
            email=intent.email,
            totp_secret=intent.totp_secret if intent.is_active else None,
            is_active=intent.is_active,
        )
        user.set_password(intent.raw_password)
        return user
