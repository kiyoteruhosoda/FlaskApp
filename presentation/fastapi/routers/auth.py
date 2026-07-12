"""認証 API エンドポイント（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/routes.py`` の auth 系
（/api/auth/login, /api/auth/logout, /api/auth/refresh, /api/auth/me 等）を移植。
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from shared.kernel.settings.settings import settings
from presentation.fastapi.dependencies.auth import get_current_principal
from presentation.fastapi.schemas.auth import (
    AuthCheckResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MeResponse,
    RefreshRequest,
    RefreshResponse,
    RoleInfo,
    SelectRoleRequest,
    ServiceAccountTokenRequest,
    ServiceAccountTokenResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
token_router = APIRouter(tags=["auth"])  # /token エンドポイント用

_bearer_scheme = HTTPBearer(auto_error=False)

JWT_BEARER_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"


# ---------------------------------------------------------------------------
# ログイン
# ---------------------------------------------------------------------------

@router.post("/login", response_model=LoginResponse)
async def api_login(
    data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """ユーザー認証して JWT アクセストークン・リフレッシュトークンを発行する。"""
    from shared.application.auth_service import AuthService
    from shared.domain.user import UserRegistrationService
    from shared.infrastructure.user_repository import SqlAlchemyUserRepository
    from presentation.fastapi.auth.totp import verify_totp
    from presentation.fastapi.services.token_service import TokenService

    user_repo = SqlAlchemyUserRepository(db)
    auth_service = AuthService(user_repo, UserRegistrationService(user_repo))

    user_model, failure_reason = auth_service.authenticate_with_reason(
        data.email, data.password
    )
    if not user_model:
        # レスポンスには理由を返さない（アカウント列挙対策）が、運用診断のため
        # サーバーログには理由コードを残す。メールアドレス等のPIIは出さない。
        logger.warning(
            "Login failed: %s",
            failure_reason,
            extra={"event": "auth.login.failed", "reason": failure_reason},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_credentials"},
        )

    if user_model.totp_secret:
        if not data.token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "totp_required"},
            )
        if not verify_totp(user_model.totp_secret, data.token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "invalid_totp"},
            )

    roles = list(getattr(user_model, "roles", []) or [])
    available_scope_set = set(getattr(user_model, "all_permissions", set()))

    granted_scope = TokenService.resolve_granted_scope(data.scope, available_scope_set)
    scope_str = " ".join(granted_scope)

    access_token, refresh_token = TokenService.generate_token_pair(
        user_model, granted_scope, session=db
    )

    requires_password_change = (
        settings.require_password_change_on_first_login
        and getattr(user_model, "must_change_password", False)
    )

    # Cookie にアクセストークンを設定
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure if hasattr(settings, "session_cookie_secure") else False,
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        requires_role_selection=len(roles) > 1,
        requires_password_change=requires_password_change,
        redirect_url=data.next or "/dashboard",
        scope=scope_str,
        available_scopes=sorted(available_scope_set),
    )


# ---------------------------------------------------------------------------
# ログアウト
# ---------------------------------------------------------------------------

@router.post("/logout", response_model=LogoutResponse)
async def api_logout(
    response: Response,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    access_token_cookie: Optional[str] = Cookie(default=None, alias="access_token"),
    db: Session = Depends(get_db),
):
    """リフレッシュトークンを無効化し、Cookie を削除する。"""
    from presentation.fastapi.services.token_service import TokenService

    # トークンを Authorization ヘッダーまたは Cookie から取得
    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif access_token_cookie:
        token = access_token_cookie

    if token:
        principal = TokenService.create_principal_from_token(token, session=db)
        if principal:
            TokenService.revoke_refresh_token(principal, session=db)

    # Cookie をクリア
    response.delete_cookie("access_token")
    response.delete_cookie("gui_access")

    return LogoutResponse(result="ok")


# ---------------------------------------------------------------------------
# トークンリフレッシュ
# ---------------------------------------------------------------------------

@router.post("/refresh", response_model=RefreshResponse)
async def api_refresh(
    data: RefreshRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    """リフレッシュトークンから新しいアクセス・リフレッシュトークンを発行する。"""
    from presentation.fastapi.services.token_service import TokenService

    token_bundle = TokenService.refresh_tokens(data.refresh_token, session=db)
    if not token_bundle:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token"},
        )

    access_token, new_refresh_token, scope_str = token_bundle

    # Cookie を更新
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
    )

    return RefreshResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="Bearer",
        scope=scope_str,
    )


# ---------------------------------------------------------------------------
# 認証チェック / ユーザー情報取得
# ---------------------------------------------------------------------------

@router.get("/check", response_model=AuthCheckResponse)
async def api_auth_check(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """JWT 認証できているか確認するシンプルなエンドポイント。"""
    from shared.infrastructure.models.user import User

    if not principal.is_individual:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required"},
        )

    user = db.get(User, principal.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required"},
        )

    return AuthCheckResponse(
        id=user.id,
        email=user.email,
        active=bool(user.is_active),
    )


@router.get("/me", response_model=MeResponse)
async def api_get_current_user(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """現在のユーザー情報と権限を取得する。"""
    from shared.infrastructure.models.user import User

    if not principal.is_individual:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required"},
        )

    user = db.get(User, principal.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required"},
        )

    roles = list(getattr(user, "roles", []) or [])
    role_data = [
        RoleInfo(
            id=role.id,
            name=role.name,
            permissions=[p.code for p in getattr(role, "permissions", [])],
        )
        for role in roles
    ]
    permissions = list(getattr(user, "all_permissions", set()) or set())

    return MeResponse(
        id=user.id,
        username=getattr(user, "username", None) or user.email,
        email=user.email,
        roles=role_data,
        active_role=None,
        permissions=permissions,
        scope=sorted(principal.scope),
        created_at=user.created_at.isoformat() if getattr(user, "created_at", None) else None,
        updated_at=user.updated_at.isoformat() if getattr(user, "updated_at", None) else None,
    )


@router.post("/select-role")
async def api_select_role(
    data: SelectRoleRequest,
    response: Response,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """アクティブロールを選択してトークンを再発行する。"""
    from shared.infrastructure.models.user import User
    from presentation.fastapi.services.token_service import TokenService

    if not principal.is_individual:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required"},
        )

    user = db.get(User, principal.id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required"},
        )

    roles = list(getattr(user, "roles", []) or [])
    selected_role = next((r for r in roles if r.id == data.role_id), None)
    if not selected_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_role"},
        )

    role_permissions = [
        p.code for p in getattr(selected_role, "permissions", []) if p.code
    ]
    access_token = TokenService.generate_access_token(user, role_permissions)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
    )

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "role": {"id": selected_role.id, "name": selected_role.name},
        "scope": " ".join(role_permissions),
    }


# ---------------------------------------------------------------------------
# サービスアカウントトークン交換
# ---------------------------------------------------------------------------

@token_router.post("/token", response_model=ServiceAccountTokenResponse)
async def api_service_account_token_exchange(
    data: ServiceAccountTokenRequest,
    db: Session = Depends(get_db),
):
    """サービスアカウントの JWT ******"""
    from presentation.fastapi.auth.service_account_auth import (
        ServiceAccountJWTError,
        ServiceAccountTokenValidator,
    )
    from presentation.fastapi.services.token_service import TokenService

    if data.grant_type != JWT_BEARER_GRANT_TYPE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "unsupported_grant_type",
                "error_description": "Only the JWT bearer grant type is supported.",
            },
        )

    audiences = settings.service_account_signing_audiences
    if not audiences:
        logger.error(
            "Service account signing audience is not configured.",
            extra={"event": "service_account.token.failed", "reason": "audience_not_configured"},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "server_error",
                "error_description": "Service account signing audience is not configured.",
            },
        )

    audience_param = audiences[0] if len(audiences) == 1 else tuple(audiences)

    try:
        account, claims = ServiceAccountTokenValidator.verify(
            data.assertion,
            audience=audience_param,
            required_scopes=None,
        )
    except ServiceAccountJWTError as exc:
        _status_map = {
            "InvalidSignature": 401,
            "ExpiredToken": 401,
            "MissingJTI": 400,
            "InvalidJTI": 400,
            "ReplayDetected": 403,
            "InvalidAudience": 403,
            "UnknownAccount": 403,
            "DisabledAccount": 403,
            "InvalidScope": 403,
            "JTICheckFailed": 500,
        }
        http_status = _status_map.get(exc.code, 403)
        raise HTTPException(
            status_code=http_status,
            detail={
                "error": "invalid_grant",
                "error_description": exc.message,
            },
        )

    if claims.get("iss") != account.name or claims.get("sub") != account.name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "invalid_grant",
                "error_description": "The assertion issuer must match the service account name.",
            },
        )

    scope_claim = claims.get("scope")
    if not isinstance(scope_claim, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_grant",
                "error_description": 'The assertion scope claim must be a string.',
            },
        )

    requested_scope = [item for item in scope_claim.split() if item]
    _, scope_str = TokenService._normalize_scope(requested_scope)
    allowed_scopes = set(account.scopes)
    disallowed = [s for s in requested_scope if s not in allowed_scopes]
    if disallowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "invalid_grant",
                "error_description": "The requested scope is not allowed for this service account.",
            },
        )

    access_token = TokenService.generate_service_account_access_token(
        account, requested_scope
    )

    return ServiceAccountTokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=TokenService.ACCESS_TOKEN_EXPIRE_SECONDS,
        scope=scope_str,
    )
