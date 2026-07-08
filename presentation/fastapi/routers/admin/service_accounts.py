"""管理者サービスアカウント管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/admin_service_accounts.py`` を移植。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

router = APIRouter(prefix="/admin/service-accounts", tags=["admin:service-accounts"])


def _require_sa_manage(principal: AuthenticatedPrincipal) -> None:
    if not principal.can("service_account:manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "service_account:manage permission required"},
        )


def _serialize_sa(sa) -> dict:
    return {
        "id": sa.service_account_id,
        "name": sa.name,
        "description": sa.description,
        "scopes": sa.scopes,
        "isActive": sa.active_flg,
        "createdAt": sa.reg_dttm.isoformat().replace("+00:00", "Z") if sa.reg_dttm else None,
        "updatedAt": sa.mod_dttm.isoformat().replace("+00:00", "Z") if sa.mod_dttm else None,
    }


@router.get("", response_model=dict)
async def api_admin_service_accounts_list(
    q: str = Query(default=""),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """サービスアカウント一覧を返す。"""
    from shared.infrastructure.models.service_account import ServiceAccount

    _require_sa_manage(principal)

    q = q.strip()
    query = db.query(ServiceAccount)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(ServiceAccount.name.ilike(like), ServiceAccount.description.ilike(like))
        )
    sas = query.order_by(ServiceAccount.service_account_id.asc()).all()
    return {"serviceAccounts": [_serialize_sa(sa) for sa in sas]}


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def api_admin_service_accounts_create(
    data: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """サービスアカウントを作成する。"""
    from shared.infrastructure.models.service_account import ServiceAccount

    _require_sa_manage(principal)

    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "name_required"},
        )
    if db.query(ServiceAccount).filter_by(name=name).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "name_exists", "message": "Service account name already in use."},
        )

    sa = ServiceAccount(
        name=name,
        description=data.get("description") or None,
        active_flg=bool(data.get("isActive", True)),
    )
    sa.set_scopes(data.get("scopes") or [])
    db.add(sa)
    db.commit()
    db.refresh(sa)
    return {"serviceAccount": _serialize_sa(sa), "created": True}


@router.get("/{sa_id}", response_model=dict)
async def api_admin_service_account_detail(
    sa_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """サービスアカウント詳細を返す。"""
    from shared.infrastructure.models.service_account import ServiceAccount

    _require_sa_manage(principal)
    sa = db.get(ServiceAccount, sa_id)
    if not sa:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    return {"serviceAccount": _serialize_sa(sa)}


@router.put("/{sa_id}", response_model=dict)
async def api_admin_service_account_update(
    sa_id: int,
    data: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """サービスアカウントを更新する。"""
    from shared.infrastructure.models.service_account import ServiceAccount

    _require_sa_manage(principal)
    sa = db.get(ServiceAccount, sa_id)
    if not sa:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    changed = False

    if "name" in data:
        new_name = (data["name"] or "").strip()
        if not new_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "name_required"},
            )
        if new_name != sa.name and db.query(ServiceAccount).filter_by(name=new_name).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "name_exists", "message": "Service account name already in use."},
            )
        sa.name = new_name
        changed = True

    if "description" in data:
        sa.description = data["description"] or None
        changed = True

    if "scopes" in data:
        sa.set_scopes(data["scopes"] or [])
        changed = True

    if "isActive" in data:
        sa.active_flg = bool(data["isActive"])
        changed = True

    if changed:
        db.commit()
        db.refresh(sa)
    return {"serviceAccount": _serialize_sa(sa), "updated": changed}


@router.delete("/{sa_id}", response_model=dict)
async def api_admin_service_account_delete(
    sa_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """サービスアカウントを削除する。"""
    from shared.infrastructure.models.service_account import ServiceAccount

    _require_sa_manage(principal)
    sa = db.get(ServiceAccount, sa_id)
    if not sa:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    db.delete(sa)
    db.commit()
    return {"result": "deleted", "id": sa_id}
