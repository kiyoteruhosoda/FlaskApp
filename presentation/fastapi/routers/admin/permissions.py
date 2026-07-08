"""管理者権限管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/admin_permissions.py`` を移植。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal
from presentation.fastapi.schemas.admin import (
    CreatePermissionRequest,
    PermissionResponse,
    UpdatePermissionRequest,
)

router = APIRouter(prefix="/admin/permissions", tags=["admin:permissions"])


def _require_permission_manage(principal: AuthenticatedPrincipal) -> None:
    if not principal.can("permission:manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "permission:manage permission required"},
        )


def _serialize_permission(perm) -> PermissionResponse:
    return PermissionResponse(
        id=perm.id,
        code=perm.code,
        detail=perm.detail,
        roleCount=len(perm.roles) if perm.roles is not None else 0,
    )


@router.get("", response_model=dict)
async def api_admin_permissions_list(
    q: str = Query(default=""),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """権限一覧を返す。"""
    from shared.infrastructure.models.user import Permission

    _require_permission_manage(principal)

    q = q.strip()
    query = db.query(Permission)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Permission.code.ilike(like), Permission.detail.ilike(like))
        )
    perms = query.order_by(Permission.code.asc()).all()
    return {"permissions": [_serialize_permission(p).model_dump() for p in perms]}


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def api_admin_permissions_create(
    data: CreatePermissionRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """権限を作成する。"""
    from shared.infrastructure.models.user import Permission

    _require_permission_manage(principal)

    code = data.code.strip()
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "code_required"},
        )
    if db.query(Permission).filter_by(code=code).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "code_exists", "message": "Permission code already in use."},
        )

    perm = Permission(code=code, detail=data.detail or None)
    db.add(perm)
    db.commit()
    db.refresh(perm)
    return {"permission": _serialize_permission(perm).model_dump(), "created": True}


@router.get("/{perm_id}", response_model=dict)
async def api_admin_permission_detail(
    perm_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """権限詳細を返す。"""
    from shared.infrastructure.models.user import Permission

    _require_permission_manage(principal)
    perm = db.get(Permission, perm_id)
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    return {"permission": _serialize_permission(perm).model_dump()}


@router.put("/{perm_id}", response_model=dict)
async def api_admin_permission_update(
    perm_id: int,
    data: UpdatePermissionRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """権限を更新する。"""
    from shared.infrastructure.models.user import Permission

    _require_permission_manage(principal)
    perm = db.get(Permission, perm_id)
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    changed = False

    if data.code is not None:
        new_code = data.code.strip()
        if not new_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "code_required"},
            )
        if new_code != perm.code and db.query(Permission).filter_by(code=new_code).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "code_exists", "message": "Permission code already in use."},
            )
        perm.code = new_code
        changed = True

    if data.detail is not None:
        perm.detail = data.detail or None
        changed = True

    if changed:
        db.commit()
        db.refresh(perm)
    return {"permission": _serialize_permission(perm).model_dump(), "updated": changed}


@router.delete("/{perm_id}", response_model=dict)
async def api_admin_permission_delete(
    perm_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """権限を削除する。"""
    from shared.infrastructure.models.user import Permission

    _require_permission_manage(principal)
    perm = db.get(Permission, perm_id)
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    db.delete(perm)
    db.commit()
    return {"result": "deleted", "id": perm_id}
