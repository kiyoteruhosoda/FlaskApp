"""ユーザースイッチ（Impersonation）API（FastAPI）。

運用管理者が他のユーザーに成り代わってアプリを操作するためのエンドポイント。
ADR-0006 参照。
"""
from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/impersonation", tags=["admin:impersonation"])

# 成り代わりセッションの有効時間（1時間）
_IMPERSONATION_TOKEN_TTL = timedelta(hours=1)


class StartImpersonationRequest(BaseModel):
    user_id: int


class StartImpersonationResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    impersonated_user_id: int
    impersonated_email: str


class EndImpersonationResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    message: str


def _record_audit(
    *,
    impersonator_id: int,
    impersonated_id: int,
    event: str,
    request: Request,
    db: Session,
) -> None:
    """成り代わりイベントを監査ログに記録する。"""
    try:
        from shared.infrastructure.models.impersonation_audit_log import ImpersonationAuditLog

        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        log_entry = ImpersonationAuditLog(
            impersonator_id=impersonator_id,
            impersonated_id=impersonated_id,
            event=event,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(log_entry)
        db.flush()
        logger.info(
            "Impersonation audit: event=%s impersonator=%s impersonated=%s ip=%s",
            event,
            impersonator_id,
            impersonated_id,
            ip_address,
            extra={
                "event": f"impersonation.{event.lower()}",
                "impersonator_id": impersonator_id,
                "impersonated_id": impersonated_id,
            },
        )
    except Exception as exc:
        logger.error("Failed to record impersonation audit log: %s", exc)


@router.post("/start", response_model=StartImpersonationResponse)
async def start_impersonation(
    data: StartImpersonationRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> StartImpersonationResponse:
    """指定ユーザーへの成り代わりセッションを開始する。

    - `admin:impersonate` 権限が必要。
    - 管理者自身・他の管理者・サービスアカウントへの成り代わりは禁止。
    - 返却トークンの TTL は 1時間（リフレッシュ不可）。
    """
    from shared.infrastructure.models.user import User
    from presentation.fastapi.services.token_service import TokenService

    if not principal.can("admin:impersonate"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "admin:impersonate permission required"},
        )

    target_user = db.get(User, data.user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "user_not_found"},
        )

    if not target_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "user_inactive", "message": "Cannot impersonate an inactive user"},
        )

    # 自分自身への成り代わり禁止
    if target_user.id == principal.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "self_impersonation", "message": "Cannot impersonate yourself"},
        )

    # 管理者ロールを持つユーザーへの成り代わり禁止（権限エスカレーション防止）
    target_roles = list(getattr(target_user, "roles", []) or [])
    target_role_names = {r.name for r in target_roles}
    if "admin" in target_role_names:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "admin_impersonation_forbidden", "message": "Cannot impersonate an admin user"},
        )

    # 対象ユーザーの権限スコープを収集
    target_permissions = list(getattr(target_user, "all_permissions", set()) or set())

    # 成り代わりトークン生成（TTL 1時間、impersonator_id クレーム付き）
    access_token = TokenService.generate_access_token(
        target_user,
        target_permissions,
    )
    # impersonator_id を埋め込むためトークンを再生成
    from datetime import datetime, timezone, timedelta
    import secrets
    from presentation.fastapi.services.token_service import TokenService as TS
    import jwt as pyjwt
    from shared.kernel.settings.settings import settings

    scope_str = " ".join(sorted(target_permissions))
    now = datetime.now(timezone.utc)
    payload = {
        "sub": f"i+{target_user.id}",
        "exp": now + _IMPERSONATION_TOKEN_TTL,
        "iat": now,
        "jti": secrets.token_urlsafe(8),
        "type": "access",
        "scope": scope_str,
        "iss": settings.access_token_issuer,
        "aud": settings.access_token_audience,
        "subject_type": "individual",
        "impersonator_id": principal.id,
    }
    access_token = TS._encode_access_token(payload)

    # 監査ログ記録
    _record_audit(
        impersonator_id=principal.id,
        impersonated_id=target_user.id,
        event="STARTED",
        request=request,
        db=db,
    )

    return StartImpersonationResponse(
        access_token=access_token,
        expires_in=int(_IMPERSONATION_TOKEN_TTL.total_seconds()),
        impersonated_user_id=target_user.id,
        impersonated_email=target_user.email,
    )


@router.post("/end", response_model=EndImpersonationResponse)
async def end_impersonation(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> EndImpersonationResponse:
    """成り代わりセッションを終了し、元の管理者トークンを再発行する。

    成り代わりトークン（impersonator_id クレームあり）を提示すること。
    """
    from shared.infrastructure.models.user import User
    from presentation.fastapi.services.token_service import TokenService
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from typing import Optional
    from fastapi import Request as FRequest

    # Authorization ヘッダーから raw トークンを取得して impersonator_id を確認
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_token"},
        )
    raw_token = auth_header.split(" ", 1)[1]

    # JWT をデコードして impersonator_id クレームを確認
    payload, err = TokenService._decode_access_token_payload(raw_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "reason": err},
        )

    impersonator_id = payload.get("impersonator_id")
    if not impersonator_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "not_impersonating", "message": "Current token is not an impersonation token"},
        )

    impersonated_id = principal.id

    # 元の管理者ユーザーを取得
    admin_user = db.get(User, int(impersonator_id))
    if not admin_user or not admin_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "admin_not_found"},
        )

    # 元の管理者として新しいアクセストークンを発行
    admin_permissions = list(getattr(admin_user, "all_permissions", set()) or set())
    new_access_token = TokenService.generate_access_token(admin_user, admin_permissions)

    # 監査ログ記録
    _record_audit(
        impersonator_id=int(impersonator_id),
        impersonated_id=impersonated_id,
        event="ENDED",
        request=request,
        db=db,
    )

    logger.info(
        "Impersonation ended: admin=%s was impersonating user=%s",
        impersonator_id,
        impersonated_id,
    )

    return EndImpersonationResponse(
        access_token=new_access_token,
        message="Impersonation ended. Restored to original admin session.",
    )


@router.get("/logs", response_model=list[dict])
async def list_impersonation_logs(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
    page: int = 1,
    page_size: int = 50,
) -> list[dict]:
    """成り代わり監査ログ一覧を返す（管理者専用）。"""
    from shared.infrastructure.models.impersonation_audit_log import ImpersonationAuditLog
    from shared.infrastructure.models.user import User

    if not principal.can("admin:system-settings"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "admin:system-settings permission required"},
        )

    offset = (page - 1) * page_size
    logs = (
        db.query(ImpersonationAuditLog)
        .order_by(ImpersonationAuditLog.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    result = []
    for log in logs:
        impersonator = db.get(User, log.impersonator_id) if log.impersonator_id else None
        impersonated = db.get(User, log.impersonated_id) if log.impersonated_id else None
        result.append({
            "id": log.id,
            "event": log.event,
            "impersonator": {
                "id": log.impersonator_id,
                "email": getattr(impersonator, "email", None),
            },
            "impersonated": {
                "id": log.impersonated_id,
                "email": getattr(impersonated, "email", None),
            },
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })

    return result
