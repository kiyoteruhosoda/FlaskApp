"""管理者グループ管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/admin_groups.py`` を移植。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal
from presentation.fastapi.schemas.admin import (
    CreateGroupRequest,
    GroupDetailResponse,
    GroupResponse,
    GroupRoleInfo,
    UpdateGroupRequest,
    UpdateGroupRolesRequest,
)

router = APIRouter(prefix="/admin/groups", tags=["admin:groups"])


def _require_user_manage(principal: AuthenticatedPrincipal) -> None:
    if not principal.can("user:manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "user:manage permission required"},
        )


def _serialize_group(group) -> GroupResponse:
    return GroupResponse(
        id=group.id,
        name=group.name,
        description=group.description,
        parentId=group.parent_id,
        parentName=group.parent.name if group.parent else None,
        memberCount=len(group.users) if group.users is not None else 0,
        childCount=len(group.children) if group.children is not None else 0,
        roles=[GroupRoleInfo(id=r.id, name=r.name) for r in (group.roles or [])],
    )


@router.get("", response_model=dict)
async def api_admin_groups_list(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """グループ一覧を返す。"""
    from shared.infrastructure.models.group import Group

    _require_user_manage(principal)
    groups = db.query(Group).order_by(Group.id.asc()).all()
    return {"groups": [_serialize_group(g).model_dump() for g in groups]}


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def api_admin_groups_create(
    data: CreateGroupRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """グループを作成する。"""
    from shared.infrastructure.models.group import Group, GroupHierarchyError

    _require_user_manage(principal)

    name = data.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "name_required"},
        )
    if db.query(Group).filter_by(name=name).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "name_exists", "message": "Group name already in use."},
        )

    group = Group(name=name, description=data.description or None)

    if data.parentId:
        parent = db.get(Group, int(data.parentId))
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "parent_not_found"},
            )
        try:
            group.assign_parent(parent)
        except GroupHierarchyError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "hierarchy_error", "message": str(e)},
            )

    db.add(group)
    db.commit()
    db.refresh(group)
    return {"group": _serialize_group(group).model_dump(), "created": True}


@router.get("/{group_id}", response_model=dict)
async def api_admin_group_detail(
    group_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """グループ詳細（メンバー一覧付き）を返す。"""
    from shared.infrastructure.models.group import Group

    _require_user_manage(principal)
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    data = _serialize_group(group).model_dump()
    data["members"] = [
        {"id": u.id, "email": u.email, "username": u.username}
        for u in (group.users or [])
    ]
    return {"group": data}


@router.put("/{group_id}", response_model=dict)
async def api_admin_group_update(
    group_id: int,
    data: UpdateGroupRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """グループを更新する。"""
    from shared.infrastructure.models.group import Group, GroupHierarchyError
    from shared.infrastructure.models.user import User

    _require_user_manage(principal)
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    changed = False

    if data.name is not None:
        new_name = data.name.strip()
        if not new_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "name_required"},
            )
        if new_name != group.name and db.query(Group).filter_by(name=new_name).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "name_exists", "message": "Group name already in use."},
            )
        group.name = new_name
        changed = True

    if data.description is not None:
        group.description = data.description or None
        changed = True

    if data.parentId is not None:
        pid = data.parentId
        if pid is None:
            group.parent = None
            changed = True
        else:
            parent = db.get(Group, int(pid))
            if not parent:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"error": "parent_not_found"},
                )
            try:
                group.assign_parent(parent)
                changed = True
            except GroupHierarchyError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "hierarchy_error", "message": str(e)},
                )

    if data.memberIds is not None:
        member_ids = data.memberIds
        members = (
            db.query(User).filter(User.id.in_(member_ids)).all()
            if member_ids
            else []
        )
        group.users = members
        changed = True

    if changed:
        db.commit()
        db.refresh(group)
    return {"group": _serialize_group(group).model_dump(), "updated": changed}


@router.delete("/{group_id}", response_model=dict)
async def api_admin_group_delete(
    group_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """グループを削除する。"""
    from shared.infrastructure.models.group import Group

    _require_user_manage(principal)
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    if group.children:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "has_children", "message": "Remove child groups first."},
        )

    db.delete(group)
    db.commit()
    return {"result": "deleted", "id": group_id}


@router.get("/{group_id}/roles", response_model=dict)
async def api_admin_group_roles_get(
    group_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """グループに付与されたロール一覧を返す。"""
    from shared.infrastructure.models.group import Group

    _require_user_manage(principal)
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    return {
        "groupId": group.id,
        "roles": [{"id": r.id, "name": r.name} for r in (group.roles or [])],
    }


@router.put("/{group_id}/roles", response_model=dict)
async def api_admin_group_roles_update(
    group_id: int,
    data: UpdateGroupRolesRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """グループに付与するロールを一括更新する。"""
    from shared.infrastructure.models.group import Group
    from shared.infrastructure.models.user import Role

    _require_user_manage(principal)
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    role_ids = data.roleIds
    if role_ids:
        roles = db.query(Role).filter(Role.id.in_(role_ids)).all()
        if len(roles) != len(set(role_ids)):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "role_not_found", "message": "One or more roles not found."},
            )
    else:
        roles = []

    group.roles = roles
    db.commit()
    return {
        "groupId": group.id,
        "roles": [{"id": r.id, "name": r.name} for r in group.roles],
        "updated": True,
    }
