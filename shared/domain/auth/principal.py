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

        try:
            permission_iterable = role.permissions  # type: ignore[attr-defined]
        except AttributeError:
            permission_iterable = ()

        for permission in permission_iterable or ():
            try:
                code = permission.code  # type: ignore[attr-defined]
            except AttributeError:
                continue
            if isinstance(code, str):
                normalized = code.strip()
                if normalized:
                    permissions.add(normalized)

        try:
            role_id = role.id  # type: ignore[attr-defined]
        except AttributeError:
            role_id = None

        try:
            role_name = role.name  # type: ignore[attr-defined]
        except AttributeError:
            role_name = None

        ordered = tuple(sorted(permissions))
        return cls(id=role_id, name=role_name, permissions=ordered)


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
        "_active_role_id",
        "_totp_secret",
        "_description",
        "_certificate_group_code",
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
        extras: MutableMapping[str, object] = dict(attributes or {})
        self._attributes = extras
        self._active_role_id = extras.get("active_role_id")
        self._totp_secret = extras.get("totp_secret")
        self._description = extras.get("description")
        self._certificate_group_code = extras.get("certificate_group_code")

    # ファクトリ
    @classmethod
    def from_user_model(
        cls,
        user,
        *,
        scope: Iterable[str] | None = None,
        active_role_id: int | None = None,
    ) -> "AuthenticatedPrincipal":
        try:
            user_id = user.id  # type: ignore[attr-defined]
        except AttributeError:
            user_id = None

        subject_id = f"i+{user_id}" if user_id is not None else "user"

        try:
            display_name = user.display_name  # type: ignore[attr-defined]
        except AttributeError:
            display_name = None
        try:
            username = user.username  # type: ignore[attr-defined]
        except AttributeError:
            username = None
        if not display_name and isinstance(username, str) and username.strip():
            display_name = username.strip()

        try:
            user_roles = user.roles  # type: ignore[attr-defined]
        except AttributeError:
            user_roles = ()
        roles = tuple(RoleSnapshot.from_model(role) for role in user_roles or ())

        if scope is None:
            try:
                all_permissions = user.all_permissions  # type: ignore[attr-defined]
            except AttributeError:
                all_permissions = set()
            permission_codes = {
                item.strip()
                for item in all_permissions
                if isinstance(item, str) and item.strip()
            }
        else:
            permission_codes = {item.strip() for item in scope if item and isinstance(item, str)}

        attributes: dict[str, object] = {}
        try:
            totp_secret = user.totp_secret  # type: ignore[attr-defined]
        except AttributeError:
            totp_secret = None
        if totp_secret:
            attributes["totp_secret"] = totp_secret
        if active_role_id is not None:
            attributes["active_role_id"] = active_role_id

        try:
            is_active_value = bool(user.is_active)  # type: ignore[attr-defined]
        except AttributeError:
            is_active_value = True

        return cls(
            subject_type="individual",
            subject_id=subject_id,
            user_id=user_id,
            name=username if isinstance(username, str) else None,
            display_name=display_name,
            roles=roles,
            permissions=permission_codes,
            is_active=is_active_value,
            attributes=attributes,
        )

    @classmethod
    def from_service_account(
        cls,
        account,
        *,
        scope: Iterable[str] | None = None,
    ) -> "AuthenticatedPrincipal":
        if scope is None:
            try:
                scopes = tuple(account.scopes)  # type: ignore[attr-defined]
            except AttributeError:
                scopes = ()
        else:
            scopes = tuple(scope)

        try:
            service_account_id = account.service_account_id  # type: ignore[attr-defined]
        except AttributeError:
            service_account_id = None

        subject_id = f"s+{service_account_id}" if service_account_id is not None else "service-account"
        attributes: dict[str, object] = {}
        try:
            description = account.description  # type: ignore[attr-defined]
        except AttributeError:
            description = None
        if description:
            attributes["description"] = description
        try:
            certificate_group_code = account.certificate_group_code  # type: ignore[attr-defined]
        except AttributeError:
            certificate_group_code = None
        if certificate_group_code:
            attributes["certificate_group_code"] = certificate_group_code

        try:
            account_name = account.name  # type: ignore[attr-defined]
        except AttributeError:
            account_name = None

        try:
            is_account_active = bool(account.active_flg)  # type: ignore[attr-defined]
        except AttributeError:
            is_account_active = True

        return cls(
            subject_type="service_account",
            subject_id=subject_id,
            service_account_id=service_account_id,
            name=account_name if isinstance(account_name, str) else None,
            display_name=account_name if isinstance(account_name, str) else None,
            permissions=scopes,
            is_active=is_account_active,
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
        active_role_id = self._active_role_id
        if active_role_id is not None:
            for role in self.roles:
                if role.id == active_role_id:
                    return role
        return self.roles[0] if self.roles else None

    @property
    def totp_secret(self) -> str | None:
        value = self._totp_secret
        if isinstance(value, str) and value.strip():
            return value
        return None

    @property
    def service_account_description(self) -> str | None:
        value = self._description
        if isinstance(value, str) and value.strip():
            return value
        return None

    @property
    def certificate_group_code(self) -> str | None:
        value = self._certificate_group_code
        if isinstance(value, str) and value.strip():
            return value
        return None

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

__all__ = [
    "AuthenticatedPrincipal",
    "RoleSnapshot",
]
