from typing import List, Optional, TYPE_CHECKING

from shared.domain.user import (
    EmailAlreadyRegisteredError,
    RegistrationIntent,
    User,
    UserRegistrationService,
)
from shared.domain.user.repository import UserRepository


if TYPE_CHECKING:
    from shared.infrastructure.models.user import User as UserModel


class AuthService:
    def __init__(
        self,
        repo: UserRepository,
        registrar: UserRegistrationService | None = None,
    ) -> None:
        self.repo = repo
        self.registrar = registrar or UserRegistrationService(repo)

    def _resolve_domain_model(self, user: User | None) -> Optional["UserModel"]:
        if user is None:
            return None
        model = getattr(user, "_model", None)
        if model is None:
            model = self.repo.get_model(user)
            if model is None:
                return None
            user.attach_model(model)
        return model

    def authenticate(self, email: str, password: str) -> Optional["UserModel"]:
        user_model, _reason = self.authenticate_with_reason(email, password)
        return user_model

    def authenticate_with_reason(
        self, email: str, password: str
    ) -> tuple[Optional["UserModel"], Optional[str]]:
        """認証に失敗した理由をあわせて返す。

        返す理由コード（クライアントには漏らさず、サーバーログの診断専用）:
        ``user_not_found`` / ``user_inactive`` / ``invalid_password``。
        """
        user = self.repo.get_by_email(email)
        if not user:
            return None, "user_not_found"
        if not user.is_active:
            return None, "user_inactive"
        if not user.check_password(password):
            return None, "invalid_password"

        return self._resolve_domain_model(user), None

    def register(self, email: str, password: str, totp_secret: str | None = None, roles: List[str] | None = None) -> User:
        intent = RegistrationIntent.create(
            email=email,
            raw_password=password,
            roles=roles or (),
            totp_secret=totp_secret,
            is_active=True,
        )
        try:
            return self.registrar.register(intent)
        except EmailAlreadyRegisteredError as exc:
            raise ValueError(str(exc)) from exc

    def register_with_pending_totp(self, email: str, password: str, roles: List[str] | None = None) -> User:
        """TOTP設定待ちのユーザーを登録（非アクティブ状態）"""
        intent = RegistrationIntent.create(
            email=email,
            raw_password=password,
            roles=roles or (),
            totp_secret=None,
            is_active=False,
        )
        try:
            return self.registrar.register(intent)
        except EmailAlreadyRegisteredError as exc:
            raise ValueError(str(exc)) from exc

    def activate_user_with_totp(self, user: User, totp_secret: str) -> User:
        """ユーザーを TOTP 設定と共にアクティブ化"""
        return self.registrar.activate_with_totp(user, totp_secret)
