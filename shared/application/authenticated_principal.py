"""Application-level representation of an authenticated principal."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, FrozenSet, Iterable, Literal, Optional, Tuple

SERVICE_ACCOUNT_SUFFIX = " (sa)"

SubjectType = Literal["individual", "system"]


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Immutable snapshot of the authenticated subject for the current request."""

    subject_type: SubjectType
    subject_id: int
    identifier: str
    scope: FrozenSet[str] = field(default_factory=frozenset)
    display_name: Optional[str] = None
    roles: Tuple[Any, ...] = ()
    email: Optional[str] = field(default=None, repr=False)
    _totp_secret: Optional[str] = field(default=None, repr=False)
    _permissions: FrozenSet[str] = field(default_factory=frozenset, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", frozenset(self.scope))
        if self._permissions:
            object.__setattr__(self, "_permissions", frozenset(self._permissions))
        else:
            object.__setattr__(self, "_permissions", self.scope)
        email = (self.email or "").strip() if isinstance(self.email, str) else ""
        object.__setattr__(self, "email", email or None)
        secret = (
            self._totp_secret.strip()
            if isinstance(self._totp_secret, str)
            else None
        )
        object.__setattr__(self, "_totp_secret", secret or None)
        if self.subject_type == "system" and self.display_name:
            normalized = self.display_name
            if not normalized.endswith(SERVICE_ACCOUNT_SUFFIX):
                normalized = f"{normalized}{SERVICE_ACCOUNT_SUFFIX}"
            object.__setattr__(self, "display_name", normalized)

    @property
    def permissions(self) -> FrozenSet[str]:
        return self._permissions

    @property
    def id(self) -> int:
        return self.subject_id

    @property
    def is_authenticated(self) -> bool:  # pragma: no cover - Flask-Login interface
        return True

    @property
    def is_active(self) -> bool:  # pragma: no cover - Flask-Login interface
        return True

    @property
    def is_anonymous(self) -> bool:  # pragma: no cover - Flask-Login interface
        return False

    def get_id(self) -> str:  # pragma: no cover - Flask-Login interface
        return f"{self.subject_type}:{self.subject_id}"

    @property
    def is_individual(self) -> bool:
        return self.subject_type == "individual"

    @property
    def is_service_account(self) -> bool:
        return self.subject_type == "system"

    def can(self, *codes: str) -> bool:
        if not codes:
            return True
        return any(code in self.permissions for code in codes)

    def with_updated_scope(self, scope: Iterable[str]) -> "AuthenticatedPrincipal":
        return AuthenticatedPrincipal(
            subject_type=self.subject_type,
            subject_id=self.subject_id,
            identifier=self.identifier,
            scope=frozenset(scope),
            display_name=self.display_name,
            roles=self.roles,
            _permissions=frozenset(scope),
        )

    @property
    def totp_secret(self) -> Optional[str]:
        return self._totp_secret

    @property
    def active_role(self) -> Optional[Any]:
        """
        Determine the active role based on current permissions.
        Returns the role whose permissions match the current scope.
        """
        if not self.roles:
            return None
        
        current_perms = set(self.permissions)
        
        # Check if any role's permissions exactly match current permissions
        for role in self.roles:
            role_perms = set(getattr(perm, "code", "") for perm in getattr(role, "permissions", []))
            if role_perms == current_perms:
                return role
        
        # If no exact match, return the first role that's a subset
        for role in self.roles:
            role_perms = set(getattr(perm, "code", "") for perm in getattr(role, "permissions", []))
            if role_perms and role_perms <= current_perms:
                return role
        
        # Default to first role if available
        return self.roles[0] if self.roles else None


__all__ = ["AuthenticatedPrincipal", "SubjectType"]
