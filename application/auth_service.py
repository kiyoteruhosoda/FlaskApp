from typing import List, Optional, TYPE_CHECKING
from domain.user.entities import User
from domain.user.repository import UserRepository


if TYPE_CHECKING:
    from core.models.user import User as UserModel


class AuthService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def _prepare_new_account(self, email: str) -> None:
        existing_user = self.repo.get_by_email(email)
        if existing_user and existing_user.is_active:
            raise ValueError("Email already exists")

        if existing_user and not existing_user.is_active:
            self.repo.delete(existing_user)

    def authenticate(self, email: str, password: str) -> Optional["UserModel"]:
        user = self.repo.get_by_email(email)
        if user and user.check_password(password) and user.is_active:
            # 認証時に取得したORMモデルを再利用できるよう返却する
            model = getattr(user, "_model", None)
            if model is None:
                model = self.repo.get_model(user)
                if model is None:
                    return None
                user.attach_model(model)
            return model
        return None

    def register(self, email: str, password: str, totp_secret: str | None = None, roles: List[str] | None = None) -> User:
        self._prepare_new_account(email)

        # TOTP設定がある場合はアクティブ、ない場合も従来通りアクティブ
        is_active = True
        user = User(email=email, totp_secret=totp_secret, is_active=is_active)
        user.set_password(password)
        return self.repo.add(user, roles or [])

    def register_with_pending_totp(self, email: str, password: str, roles: List[str] | None = None) -> User:
        """TOTP設定待ちのユーザーを登録（非アクティブ状態）"""
        self._prepare_new_account(email)

        # 非アクティブ状態で登録
        user = User(email=email, totp_secret=None, is_active=False)
        user.set_password(password)
        return self.repo.add(user, roles or [])

    def activate_user_with_totp(self, user: User, totp_secret: str) -> User:
        """ユーザーを TOTP 設定と共にアクティブ化"""
        user.totp_secret = totp_secret
        user.is_active = True
        return self.repo.update(user)
