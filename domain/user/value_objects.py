"""ユーザードメインで利用する値オブジェクト。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple


@dataclass(frozen=True)
class RegistrationIntent:
    """ユーザー登録のリクエスト内容を表す値オブジェクト。"""

    email: str
    raw_password: str
    roles: Tuple[str, ...] = ()
    totp_secret: str | None = None
    is_active: bool = True

    def __post_init__(self) -> None:
        normalized_roles = tuple(self.roles)
        object.__setattr__(self, "roles", normalized_roles)

    @classmethod
    def create(
        cls,
        *,
        email: str,
        raw_password: str,
        roles: Iterable[str] | None = None,
        totp_secret: str | None = None,
        is_active: bool = True,
    ) -> "RegistrationIntent":
        return cls(
            email=email,
            raw_password=raw_password,
            roles=tuple(roles or ()),
            totp_secret=totp_secret,
            is_active=is_active,
        )
