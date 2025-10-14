"""Shared infrastructure components."""

from .user_repository import SqlAlchemyUserRepository

__all__ = [
    "SqlAlchemyUserRepository",
]
