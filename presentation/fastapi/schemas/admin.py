"""管理者系エンドポイント用 Pydantic スキーマ。"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr


# ---------------------------------------------------------------------------
# ユーザー
# ---------------------------------------------------------------------------

class UserRoleInfo(BaseModel):
    id: int
    name: str


class UserResponse(BaseModel):
    id: int
    email: str
    username: str | None
    isActive: bool
    hasTOTP: bool
    mustChangePassword: bool
    createdAt: str | None
    roles: list[UserRoleInfo]


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    username: str | None = None
    roleIds: list[int] = []
    mustChangePassword: bool = False


class UpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    username: str | None = None
    isActive: bool | None = None
    mustChangePassword: bool | None = None


class UpdateUserRolesRequest(BaseModel):
    roleIds: list[int]


# ---------------------------------------------------------------------------
# ロール
# ---------------------------------------------------------------------------

class PermissionInfo(BaseModel):
    id: int
    code: str


class RoleResponse(BaseModel):
    id: int
    name: str
    permissions: list[PermissionInfo]
    userCount: int
    isDefault: bool


class CreateRoleRequest(BaseModel):
    name: str
    permissionIds: list[int] = []


class UpdateRoleRequest(BaseModel):
    name: str | None = None
    permissionIds: list[int] | None = None


# ---------------------------------------------------------------------------
# グループ
# ---------------------------------------------------------------------------

class GroupRoleInfo(BaseModel):
    id: int
    name: str


class GroupResponse(BaseModel):
    id: int
    name: str
    description: str | None
    parentId: int | None
    parentName: str | None
    memberCount: int
    childCount: int
    roles: list[GroupRoleInfo]


class GroupDetailResponse(GroupResponse):
    members: list[dict]


class CreateGroupRequest(BaseModel):
    name: str
    description: str | None = None
    parentId: int | None = None


class UpdateGroupRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    parentId: int | None = None
    memberIds: list[int] | None = None


class UpdateGroupRolesRequest(BaseModel):
    roleIds: list[int]


# ---------------------------------------------------------------------------
# 権限
# ---------------------------------------------------------------------------

class PermissionResponse(BaseModel):
    id: int
    code: str
    detail: str | None
    roleCount: int


class CreatePermissionRequest(BaseModel):
    code: str
    detail: str | None = None


class UpdatePermissionRequest(BaseModel):
    code: str | None = None
    detail: str | None = None


# ---------------------------------------------------------------------------
# サービスアカウント
# ---------------------------------------------------------------------------

class ServiceAccountResponse(BaseModel):
    id: str
    name: str
    isActive: bool
    scopes: list[str]
    createdAt: str | None


class CreateServiceAccountRequest(BaseModel):
    name: str
    scopes: list[str] = []


class UpdateServiceAccountRequest(BaseModel):
    name: str | None = None
    scopes: list[str] | None = None
    isActive: bool | None = None


__all__ = [
    "UserResponse",
    "UserRoleInfo",
    "CreateUserRequest",
    "UpdateUserRequest",
    "UpdateUserRolesRequest",
    "RoleResponse",
    "PermissionInfo",
    "CreateRoleRequest",
    "UpdateRoleRequest",
    "GroupResponse",
    "GroupDetailResponse",
    "CreateGroupRequest",
    "UpdateGroupRequest",
    "UpdateGroupRolesRequest",
    "GroupRoleInfo",
    "PermissionResponse",
    "CreatePermissionRequest",
    "UpdatePermissionRequest",
    "ServiceAccountResponse",
    "CreateServiceAccountRequest",
    "UpdateServiceAccountRequest",
]
