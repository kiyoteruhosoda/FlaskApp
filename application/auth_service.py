from typing import List, Optional
from domain.user.entities import User
from domain.user.repository import UserRepository


class AuthService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    def authenticate(self, email: str, password: str) -> Optional[User]:
        user = self.repo.get_by_email(email)
        if user and user.check_password(password):
            return user
        return None

    def register(self, email: str, password: str, totp_secret: str | None = None, roles: List[str] | None = None) -> User:
        if self.repo.get_by_email(email):
            raise ValueError("Email already exists")
        user = User(email=email, totp_secret=totp_secret)
        user.set_password(password)
        return self.repo.add(user, roles or [])
