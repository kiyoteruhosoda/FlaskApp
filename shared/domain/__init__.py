"""Shared domain model."""

from .user import (
    EmailAlreadyRegisteredError,
    RegistrationIntent,
    User,
    UserRegistrationService,
)
from .auth.principal import AuthenticatedPrincipal, RoleSnapshot

__all__ = [
    "EmailAlreadyRegisteredError",
    "RegistrationIntent",
    "User",
    "UserRegistrationService",
    "AuthenticatedPrincipal",
    "RoleSnapshot",
]
