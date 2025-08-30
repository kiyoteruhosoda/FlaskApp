from typing import List, Optional
from domain.user.entities import User
from domain.user.repository import UserRepository


class AuthService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def authenticate(self, email: str, password: str) -> Optional[User]:
        user = self.repo.get_by_email(email)
        if user and user.check_password(password) and user.is_active:
            return user
        return None

    def register(self, email: str, password: str, totp_secret: str | None = None, roles: List[str] | None = None) -> User:
        # 既存の非アクティブユーザーをチェック
        existing_user = self.repo.get_by_email(email)
        if existing_user and existing_user.is_active:
            raise ValueError("Email already exists")
        
        # 非アクティブユーザーが存在する場合は削除
        if existing_user and not existing_user.is_active:
            self.repo.delete(existing_user)
        
        # TOTP設定がある場合はアクティブ、ない場合も従来通りアクティブ
        is_active = True
        user = User(email=email, totp_secret=totp_secret, is_active=is_active)
        user.set_password(password)
        return self.repo.add(user, roles or [])

    def register_with_pending_totp(self, email: str, password: str, roles: List[str] | None = None) -> User:
        """TOTP設定待ちのユーザーを登録（非アクティブ状態）"""
        # 既存の非アクティブユーザーをチェック
        existing_user = self.repo.get_by_email(email)
        if existing_user and existing_user.is_active:
            raise ValueError("Email already exists")
        
        # 非アクティブユーザーが存在する場合は削除
        if existing_user and not existing_user.is_active:
            self.repo.delete(existing_user)
        
        # 非アクティブ状態で登録
        user = User(email=email, totp_secret=None, is_active=False)
        user.set_password(password)
        return self.repo.add(user, roles or [])

    def activate_user_with_totp(self, user: User, totp_secret: str) -> User:
        """ユーザーを TOTP 設定と共にアクティブ化"""
        user.totp_secret = totp_secret
        user.is_active = True
        return self.repo.update(user)
