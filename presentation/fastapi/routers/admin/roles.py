"""管理者ロール管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/admin_roles.py`` を移植。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal
from presentation.fastapi.schemas.admin import (
    CreateRoleRequest,
    PermissionInfo,
    RoleResponse,
    UpdateRoleRequest,
)

router = APIRouter(prefix="/admin/roles", tags=["admin:roles"])


def _require_user_manage(principal: AuthenticatedPrincipal) -> None:
    if not principal.can("user:manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "user:manage permission required"},
        )


def _default_role_names():
    from shared.domain.auth.master_data import ROLES
    return frozenset(name for _, name in ROLES)


def _reject_default_role_mutation(role) -> None:
    if role.name in _default_role_names():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "default_role_immutable",
                "message": "Default roles cannot be modified or deleted.",
            },
        )


def _serialize_role(role) -> RoleResponse:
    default_names = _default_role_names()
    return RoleResponse(
        id=role.id,
        name=role.name,
        permissions=[
            PermissionInfo(id=p.id, code=p.code) for p in (role.permissions or [])
        ],
        userCount=len(role.users) if role.users is not None else 0,
        isDefault=role.name in default_names,
    )


@router.get("", response_model=dict)
async def api_admin_roles_list(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ロール一覧を返す。"""
    from shared.infrastructure.models.user import Role

    _require_user_manage(principal)
    roles = db.query(Role).order_by(Role.id.asc()).all()
    return {"roles": [_serialize_role(r).model_dump() for r in roles]}


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def api_admin_roles_create(
    data: CreateRoleRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ロールを作成する。"""
    from shared.infrastructure.models.user import Role, Permission

    _require_user_manage(principal)

    name = data.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "name_required"},
        )
    if db.query(Role).filter_by(name=name).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "name_exists", "message": "Role name already in use."},
        )

    perms: list[Permission] = []
    if data.permissionIds:
        perms = db.query(Permission).filter(Permission.id.in_(data.permissionIds)).all()

    role = Role(name=name)
    role.permissions = perms
    db.add(role)
    db.commit()
    db.refresh(role)
    return {"role": _serialize_role(role).model_dump(), "created": True}


@router.get("/{role_id}", response_model=dict)
async def api_admin_role_detail(
    role_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ロール詳細を返す。"""
    from shared.infrastructure.models.user import Role

    _require_user_manage(principal)
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    return {"role": _serialize_role(role).model_dump()}


@router.put("/{role_id}", response_model=dict)
async def api_admin_role_update(
    role_id: int,
    data: UpdateRoleRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ロール名と権限を更新する。"""
    from shared.infrastructure.models.user import Role, Permission

    _require_user_manage(principal)
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    _reject_default_role_mutation(role)
    changed = False

    if data.name is not None:
        new_name = data.name.strip()
        if not new_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "name_required"},
            )
        if new_name != role.name and db.query(Role).filter_by(name=new_name).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "name_exists", "message": "Role name already in use."},
            )
        role.name = new_name
        changed = True

    if data.permissionIds is not None:
        perm_ids = data.permissionIds
        perms = (
            db.query(Permission).filter(Permission.id.in_(perm_ids)).all()
            if perm_ids
            else []
        )
        role.permissions = perms
        changed = True

    if changed:
        db.commit()
        db.refresh(role)
    return {"role": _serialize_role(role).model_dump(), "updated": changed}


@router.delete("/{role_id}", response_model=dict)
async def api_admin_role_delete(
    role_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ロールを削除する。"""
    from shared.infrastructure.models.user import Role

    _require_user_manage(principal)
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    _reject_default_role_mutation(role)
    db.delete(role)
    db.commit()
    return {"result": "deleted", "id": role_id}
