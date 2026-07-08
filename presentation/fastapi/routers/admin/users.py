"""管理者ユーザー管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/admin_users.py`` を移植。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal
from presentation.fastapi.schemas.admin import (
    CreateUserRequest,
    UpdateUserRequest,
    UpdateUserRolesRequest,
    UserResponse,
    UserRoleInfo,
)

router = APIRouter(prefix="/admin/users", tags=["admin:users"])


def _require_user_manage(principal: AuthenticatedPrincipal) -> None:
    if not principal.can("user:manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "user:manage permission required"},
        )


def _serialize_user(user) -> UserResponse:
    from shared.infrastructure.models.user import User

    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        isActive=bool(user.is_active),
        hasTOTP=bool(user.totp_secret),
        mustChangePassword=bool(getattr(user, "must_change_password", False)),
        createdAt=(
            user.created_at.isoformat().replace("+00:00", "Z")
            if user.created_at
            else None
        ),
        roles=[UserRoleInfo(id=r.id, name=r.name) for r in (user.roles or [])],
    )


def _is_valid_email(email: str) -> bool:
    """メールアドレスの基本バリデーション。"""
    from marshmallow.validate import Email as EmailValidator
    from marshmallow import ValidationError as MarshmallowValidationError

    try:
        EmailValidator()(email)
        return True
    except MarshmallowValidationError:
        return False


@router.get("", response_model=dict)
async def api_admin_users_list(
    q: str = Query(default=""),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ユーザー一覧を返す（``user:manage`` 権限必須）。"""
    from shared.infrastructure.models.user import User

    _require_user_manage(principal)

    q = q.strip()
    query = db.query(User)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(User.email.ilike(like), User.username.ilike(like))
        )
    users = query.order_by(User.id.asc()).all()
    return {"users": [_serialize_user(u).model_dump() for u in users]}


@router.get("/{user_id}", response_model=dict)
async def api_admin_user_detail(
    user_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ユーザー詳細を返す。"""
    from shared.infrastructure.models.user import User

    _require_user_manage(principal)

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    return {"user": _serialize_user(user).model_dump()}


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def api_admin_users_create(
    data: CreateUserRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ユーザーを作成する。"""
    from shared.infrastructure.models.user import User, Role

    _require_user_manage(principal)

    email = data.email.strip()
    if not _is_valid_email(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_email", "message": "Please provide a valid email address."},
        )
    if not data.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "password_required"},
        )
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "email_exists", "message": "Email already in use."},
        )

    roles: list[Role] = []
    if data.roleIds:
        roles = db.query(Role).filter(Role.id.in_(data.roleIds)).all()
        if len(roles) != len(set(data.roleIds)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_role"},
            )

    user = User(email=email, username=data.username or None)
    user.set_password(data.password)
    user.roles = roles
    if data.mustChangePassword:
        user.must_change_password = True
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user": _serialize_user(user).model_dump(), "created": True}


@router.put("/{user_id}", response_model=dict)
async def api_admin_user_update(
    user_id: int,
    data: UpdateUserRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ユーザーのプロフィールを更新する。"""
    from shared.infrastructure.models.user import User

    _require_user_manage(principal)

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    changed = False

    if data.email is not None:
        new_email = str(data.email).strip()
        if not new_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "email_required"},
            )
        if not _is_valid_email(new_email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_email", "message": "Please provide a valid email address."},
            )
        if new_email != user.email and db.query(User).filter_by(email=new_email).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "email_exists", "message": "Email already in use."},
            )
        user.email = new_email
        changed = True

    if data.username is not None:
        user.username = data.username or None
        changed = True

    if data.isActive is not None:
        if user.id == principal.id and not data.isActive:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "cannot_deactivate_self"},
            )
        user.is_active = bool(data.isActive)
        changed = True

    if data.mustChangePassword is not None:
        user.must_change_password = bool(data.mustChangePassword)
        changed = True

    if changed:
        db.commit()
        db.refresh(user)
    return {"user": _serialize_user(user).model_dump(), "updated": changed}


@router.put("/{user_id}/roles", response_model=dict)
async def api_admin_user_roles(
    user_id: int,
    data: UpdateUserRolesRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ユーザーのロール割り当てを更新する。"""
    from shared.infrastructure.models.user import User, Role

    _require_user_manage(principal)

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    if not data.roleIds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "at_least_one_role_required"},
        )

    roles = db.query(Role).filter(Role.id.in_(data.roleIds)).all()
    if len(roles) != len(set(data.roleIds)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_role"},
        )

    user.roles = roles
    db.commit()
    db.refresh(user)
    return {"user": _serialize_user(user).model_dump(), "updated": True}


@router.post("/{user_id}/reset-totp", response_model=dict)
async def api_admin_user_reset_totp(
    user_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ユーザーの TOTP シークレットをリセットする。"""
    from shared.infrastructure.models.user import User

    _require_user_manage(principal)

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    user.totp_secret = None
    db.commit()
    return {"result": "reset", "userId": user_id}


@router.delete("/{user_id}", response_model=dict)
async def api_admin_user_delete(
    user_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ユーザーを削除する。"""
    from shared.infrastructure.models.user import User

    _require_user_manage(principal)

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    if principal.id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "cannot_delete_self"},
        )

    db.delete(user)
    db.commit()
    return {"result": "deleted", "userId": user_id}
