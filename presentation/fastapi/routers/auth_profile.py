"""認証プロフィール API（FastAPI）。

プロフィール更新・2FA 設定・新規登録・パスワードリセット。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal, get_optional_principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth:profile"])


def _get_orm_user(principal: AuthenticatedPrincipal, db: Session):
    """principal の user_id から SQLAlchemy User を取得する。"""
    from shared.infrastructure.models.user import User

    user = db.get(User, int(principal.user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "user_not_found"},
        )
    return user


@router.put("/profile")
async def api_auth_profile_update(
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """現在のユーザーのプロフィール（email / username / password）を更新する。"""
    from shared.infrastructure.models.user import User

    user = _get_orm_user(principal, db)
    changed = False

    if "email" in body:
        new_email = (body["email"] or "").strip()
        if not new_email:
            raise HTTPException(status_code=400, detail={"error": "email_required"})
        if new_email != user.email and db.query(User).filter_by(email=new_email).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "email_exists", "message": "Email already in use."},
            )
        user.email = new_email
        changed = True

    if "username" in body:
        user.username = body["username"] or None
        changed = True

    if "password" in body:
        new_password = (body["password"] or "").strip()
        if new_password:
            if len(new_password) < 8:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "password_too_short", "message": "Password must be at least 8 characters."},
                )
            user.set_password(new_password)
            changed = True

    if changed:
        db.commit()

    return {
        "updated": changed,
        "user": {"id": user.id, "email": user.email, "username": user.username},
    }


@router.get("/2fa/status")
async def api_auth_2fa_status(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """現在のユーザーの 2FA 有効状態を返す。"""
    user = _get_orm_user(principal, db)
    return {"enabled": bool(user.totp_secret)}


@router.post("/2fa/setup")
async def api_auth_2fa_setup(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """新しい TOTP シークレットを生成して返す。"""
    from presentation.web.auth.totp import new_totp_secret, provisioning_uri, qr_code_data_uri

    user = _get_orm_user(principal, db)
    if user.totp_secret:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "already_enabled"})

    secret = new_totp_secret()
    uri = provisioning_uri(user.email, secret)
    qr_data = qr_code_data_uri(uri)
    return {"secret": secret, "otpauth_uri": uri, "qr_data_uri": qr_data}


@router.post("/2fa/confirm")
async def api_auth_2fa_confirm(
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """TOTP コードを検証してシークレットを保存する（2FA を有効化）。"""
    from presentation.web.auth.totp import verify_totp

    user = _get_orm_user(principal, db)
    if user.totp_secret:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "already_enabled"})

    secret = (body.get("secret") or "").strip()
    code = (body.get("code") or "").strip()
    if not secret:
        raise HTTPException(status_code=400, detail={"error": "secret_required"})
    if not code:
        raise HTTPException(status_code=400, detail={"error": "code_required"})
    if not verify_totp(secret, code):
        raise HTTPException(status_code=400, detail={"error": "invalid_code"})

    user.totp_secret = secret
    db.commit()
    return {"enabled": True}


@router.delete("/2fa")
async def api_auth_2fa_disable(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """2FA を無効化する。"""
    user = _get_orm_user(principal, db)
    user.totp_secret = None
    db.commit()
    return {"enabled": False}


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def api_auth_register(
    body: dict,
    db: Session = Depends(get_db),
):
    """新しいユーザーを登録して JWT トークンを発行する。"""
    from shared.infrastructure.models.user import User, Role
    from presentation.web.services.token_service import TokenService

    email = (body.get("email") or "").strip()
    password = (body.get("password") or "").strip()

    if not email:
        raise HTTPException(status_code=400, detail={"error": "email_required"})
    if not password:
        raise HTTPException(status_code=400, detail={"error": "password_required"})
    if len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail={"error": "password_too_short", "message": "Password must be at least 8 characters."},
        )
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "email_exists", "message": "Email already in use."},
        )

    user = User(email=email, username=body.get("username") or None, is_active=True)
    user.set_password(password)

    guest_role = db.query(Role).filter_by(name="guest").first()
    if guest_role:
        user.roles = [guest_role]

    db.add(user)
    db.commit()
    db.refresh(user)

    granted_scope = sorted(user.all_permissions)
    access_token, refresh_token = TokenService.generate_token_pair(user, granted_scope, session=db)

    return {
        "user": {"id": user.id, "email": user.email, "username": user.username},
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
    }


@router.post("/password/forgot")
async def api_auth_password_forgot(body: dict, db: Session = Depends(get_db)):
    """パスワードリセットメールを送信する。"""
    from presentation.web.services.password_reset_service import PasswordResetService

    email = (body.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail={"error": "email_required"})
    ok, err = PasswordResetService.create_reset_request(email)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "mail_disabled", "message": err},
        )
    return {"sent": True}


@router.post("/password/reset")
async def api_auth_password_reset(body: dict, db: Session = Depends(get_db)):
    """トークンを検証して新しいパスワードを設定する。"""
    from presentation.web.services.password_reset_service import PasswordResetService

    token = (body.get("token") or "").strip()
    password = body.get("password") or ""
    if not token:
        raise HTTPException(status_code=400, detail={"error": "token_required"})
    if not password or len(password) < 8:
        raise HTTPException(status_code=400, detail={"error": "password_too_short"})
    ok = PasswordResetService.reset_password(token, password)
    if not ok:
        raise HTTPException(status_code=400, detail={"error": "invalid_token"})
    return {"reset": True}


@router.post("/password/force-change")
async def api_auth_password_force_change(
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """初回ログイン時の強制パスワード変更。"""
    user = _get_orm_user(principal, db)

    new_password = (body.get("password") or "").strip()
    if not new_password:
        raise HTTPException(status_code=400, detail={"error": "password_required"})
    if len(new_password) < 8:
        raise HTTPException(
            status_code=400,
            detail={"error": "password_too_short", "message": "Password must be at least 8 characters."},
        )

    current_password = (body.get("current_password") or "").strip()
    if current_password and not user.check_password(current_password):
        raise HTTPException(status_code=400, detail={"error": "invalid_current_password"})

    user.set_password(new_password)
    user.must_change_password = False
    db.commit()
    return {"changed": True}
