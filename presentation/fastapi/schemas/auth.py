"""認証エンドポイント用 Pydantic スキーマ。

Flask-Smorest 時代の Marshmallow スキーマ
(`presentation/web/api/schemas/auth.py`) を Pydantic v2 で再実装。
"""
from __future__ import annotations

from typing import Any, Union

from pydantic import BaseModel, EmailStr, field_validator


# ---------------------------------------------------------------------------
# ヘルパー型
# ---------------------------------------------------------------------------

def _normalize_scope(value: Any) -> list[str]:
    """スコープ入力を文字列リストに正規化する。"""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [item for item in value.split() if item]
    if isinstance(value, (list, tuple, set, frozenset)):
        result: list[str] = []
        for item in value:
            if isinstance(item, str):
                token = item.strip()
                if token:
                    result.append(token)
        return result
    return []


# ---------------------------------------------------------------------------
# リクエストスキーマ
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    """``POST /api/auth/login`` リクエスト。"""

    email: EmailStr
    password: str
    token: str | None = None
    scope: list[str] = []
    active_role_id: int | None = None
    next: str | None = None

    @field_validator("scope", mode="before")
    @classmethod
    def _coerce_scope(cls, v: Any) -> list[str]:
        return _normalize_scope(v)

    @field_validator("password")
    @classmethod
    def _password_not_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("password is required")
        return v


class RefreshRequest(BaseModel):
    """``POST /api/auth/refresh`` リクエスト。"""

    refresh_token: str


class SelectRoleRequest(BaseModel):
    """``POST /api/auth/select-role`` リクエスト。"""

    role_id: int


class ServiceAccountTokenRequest(BaseModel):
    """``POST /api/token`` サービスアカウントトークン交換リクエスト。"""

    grant_type: str
    assertion: str


# ---------------------------------------------------------------------------
# レスポンススキーマ
# ---------------------------------------------------------------------------

class LoginResponse(BaseModel):
    """``POST /api/auth/login`` レスポンス。"""

    access_token: str
    refresh_token: str
    token_type: str
    requires_role_selection: bool
    requires_password_change: bool = False
    redirect_url: str
    scope: str
    available_scopes: list[str]


class RefreshResponse(BaseModel):
    """``POST /api/auth/refresh`` レスポンス。"""

    access_token: str
    refresh_token: str
    token_type: str
    scope: str


class LogoutResponse(BaseModel):
    """``POST /api/auth/logout`` レスポンス。"""

    result: str


class ServiceAccountTokenResponse(BaseModel):
    """``POST /api/token`` レスポンス。"""

    access_token: str
    token_type: str
    expires_in: int
    scope: str


class AuthCheckResponse(BaseModel):
    """``GET /api/auth/check`` レスポンス。"""

    id: int
    email: str
    active: bool


class RoleInfo(BaseModel):
    id: int
    name: str
    permissions: list[str] = []


class RolesResponse(BaseModel):
    """``GET /api/auth/roles`` レスポンス。

    ``active_role_id`` は現在のトークンの scope がいずれかのロールの権限
    セットと一致する場合のみ設定される（select-role 実行後の状態）。
    ``requires_selection`` は複数ロール保有時に true。
    """

    roles: list[RoleInfo]
    active_role_id: int | None = None
    requires_selection: bool


class MeResponse(BaseModel):
    """``GET /api/auth/me`` レスポンス。

    ``permissions`` はDB上の保有権限（ロールの和集合）、``scope`` は現在の
    アクセストークンに実際に交付されている実効権限。JWT 発行時に scope を
    絞った場合や、発行後に権限が付与された場合は ``scope`` の方が狭くなる。
    """

    id: int
    username: str
    email: str
    roles: list[RoleInfo]
    active_role: RoleInfo | None = None
    permissions: list[str]
    scope: list[str] = []
    created_at: str | None = None
    updated_at: str | None = None


__all__ = [
    "LoginRequest",
    "LoginResponse",
    "LogoutResponse",
    "RefreshRequest",
    "RefreshResponse",
    "SelectRoleRequest",
    "ServiceAccountTokenRequest",
    "ServiceAccountTokenResponse",
    "AuthCheckResponse",
    "MeResponse",
    "RoleInfo",
    "RolesResponse",
]
