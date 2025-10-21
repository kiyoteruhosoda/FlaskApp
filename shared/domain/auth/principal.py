from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, MutableMapping, Sequence

from flask_login import UserMixin


@dataclass(frozen=True, slots=True)
class RoleSnapshot:
    """軽量なロール情報のスナップショット。"""

    id: int | None
    name: str | None
    permissions: tuple[str, ...] = ()

    @classmethod
    def from_model(cls, role) -> "RoleSnapshot":
        permissions: set[str] = set()
        for permission in getattr(role, "permissions", []) or []:
            code = getattr(permission, "code", None)
            if isinstance(code, str) and code.strip():
                permissions.add(code.strip())
        ordered = tuple(sorted(permissions))
        return cls(id=getattr(role, "id", None), name=getattr(role, "name", None), permissions=ordered)


class AuthenticatedPrincipal(UserMixin):
    """Flaskアプリ内で扱う認証済み主体の情報を保持する値オブジェクト。"""

    __slots__ = (
        "subject_type",
        "subject_id",
        "user_id",
        "service_account_id",
        "name",
        "_display_name",
        "roles",
        "permissions",
        "_is_active",
        "_attributes",
    )

    def __init__(
        self,
        *,
        subject_type: str,
        subject_id: str,
        user_id: int | None = None,
        service_account_id: int | None = None,
        name: str | None = None,
        display_name: str | None = None,
        roles: Sequence[RoleSnapshot] | None = None,
        permissions: Iterable[str] | None = None,
        is_active: bool = True,
        attributes: Mapping[str, object] | None = None,
    ) -> None:
        normalized_type = (subject_type or "unknown").strip() or "unknown"
        normalized_id = (subject_id or "").strip()
        if not normalized_id:
            raise ValueError("subject_id must be provided for AuthenticatedPrincipal")

        self.subject_type = normalized_type
        self.subject_id = normalized_id
        self.user_id = user_id
        self.service_account_id = service_account_id
        self.name = name
        self._display_name = display_name
        self.roles: tuple[RoleSnapshot, ...] = tuple(roles or ())
        self.permissions = frozenset(item.strip() for item in (permissions or []) if item and item.strip())
        self._is_active = bool(is_active)
        self._attributes: MutableMapping[str, object] = dict(attributes or {})

    # ファクトリ
    @classmethod
    def from_user_model(
        cls,
        user,
        *,
        scope: Iterable[str] | None = None,
        active_role_id: int | None = None,
    ) -> "AuthenticatedPrincipal":
        subject_id = f"i+{user.id}" if getattr(user, "id", None) is not None else "user"
        display_name = getattr(user, "display_name", None)
        if not display_name:
            username = getattr(user, "username", None)
            if isinstance(username, str) and username.strip():
                display_name = username.strip()

        roles = tuple(RoleSnapshot.from_model(role) for role in getattr(user, "roles", []) or [])

        if scope is None:
            permission_codes = set(getattr(user, "all_permissions", set()) or set())
        else:
            permission_codes = {item.strip() for item in scope if item and isinstance(item, str)}

        attributes: dict[str, object] = {}
        totp_secret = getattr(user, "totp_secret", None)
        if totp_secret:
            attributes["totp_secret"] = totp_secret
        if active_role_id is not None:
            attributes["active_role_id"] = active_role_id

        return cls(
            subject_type="individual",
            subject_id=subject_id,
            user_id=getattr(user, "id", None),
            name=getattr(user, "username", None),
            display_name=display_name,
            roles=roles,
            permissions=permission_codes,
            is_active=bool(getattr(user, "is_active", True)),
            attributes=attributes,
        )

    @classmethod
    def from_service_account(
        cls,
        account,
        *,
        scope: Iterable[str] | None = None,
    ) -> "AuthenticatedPrincipal":
        scopes = scope if scope is not None else getattr(account, "scopes", [])
        subject_id = (
            f"s+{account.service_account_id}"
            if getattr(account, "service_account_id", None) is not None
            else "service-account"
        )
        attributes: dict[str, object] = {}
        description = getattr(account, "description", None)
        if description:
            attributes["description"] = description
        certificate_group_code = getattr(account, "certificate_group_code", None)
        if certificate_group_code:
            attributes["certificate_group_code"] = certificate_group_code

        return cls(
            subject_type="service_account",
            subject_id=subject_id,
            service_account_id=getattr(account, "service_account_id", None),
            name=getattr(account, "name", None),
            display_name=getattr(account, "name", None),
            permissions=scopes,
            is_active=bool(getattr(account, "active_flg", True)),
            attributes=attributes,
        )

    # Flask-Login互換API
    def get_id(self) -> str:
        return self.subject_id

    @property
    def id(self):  # noqa: D401 - Flask-Loginと互換のため単純に返す
        """内部識別子（ユーザーIDまたはサービスアカウントID）を返す。"""
        if self.user_id is not None:
            return self.user_id
        return self.service_account_id

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def is_authenticated(self) -> bool:  # pragma: no cover - UserMixinとの整合性
        return True

    @property
    def is_anonymous(self) -> bool:  # pragma: no cover - UserMixinとの整合性
        return False

    @property
    def display_name(self) -> str | None:
        if self._display_name:
            base = self._display_name
        elif self.name:
            base = self.name
        else:
            base = self.subject_id

        if self.subject_type == "system" and base and not base.endswith(" (sa)"):
            return f"{base} (sa)"
        return base

    @property
    def active_role(self):
        active_role_id = self._attributes.get("active_role_id")
        if active_role_id is not None:
            for role in self.roles:
                if role.id == active_role_id:
                    return role
        return self.roles[0] if self.roles else None

    def can(self, *codes: str) -> bool:
        normalized = [code for code in (codes or []) if isinstance(code, str) and code]
        if not normalized:
            return False
        permission_set = self.permissions
        return any(code in permission_set for code in normalized)

    def to_dict(self) -> dict[str, object]:
        return {
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "user_id": self.user_id,
            "service_account_id": self.service_account_id,
            "name": self.name,
            "display_name": self.display_name,
            "roles": [role.__dict__ for role in self.roles],
            "permissions": sorted(self.permissions),
            "is_active": self.is_active,
        }

    def __getattr__(self, item: str):
        try:
            return self._attributes[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


__all__ = [
    "AuthenticatedPrincipal",
    "RoleSnapshot",
]
