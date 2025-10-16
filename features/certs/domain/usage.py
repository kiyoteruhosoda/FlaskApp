"""証明書用途に関する定義"""
from __future__ import annotations

from enum import Enum


class UsageType(str, Enum):
    """証明書の利用用途"""

    SERVER_SIGNING = "server_signing"
    CLIENT_SIGNING = "client_signing"
    ENCRYPTION = "encryption"

    @classmethod
    def from_str(cls, value: str | None) -> "UsageType":
        """文字列から用途を解決"""

        if value is None:
            return cls.SERVER_SIGNING
        try:
            return cls(value)
        except ValueError as exc:  # noqa: B904 - Enum変換失敗時はValueErrorで十分
            raise ValueError(f"未知のusageTypeです: {value}") from exc
