from __future__ import annotations
from typing import Protocol, Optional, List
from .entities import User


class UserRepository(Protocol):
    def get_by_email(self, email: str) -> Optional[User]:
        ...

    def add(self, user: User, role_names: List[str]) -> User:
        ...

    def get_model(self, user: User):
        """Return the underlying ORM model for the given domain user."""
        ...
