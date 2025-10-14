"""Shared domain model."""

from .user import (
    EmailAlreadyRegisteredError,
    RegistrationIntent,
    User,
    UserRegistrationService,
)

__all__ = [
    "EmailAlreadyRegisteredError",
    "RegistrationIntent",
    "User",
    "UserRegistrationService",
]
