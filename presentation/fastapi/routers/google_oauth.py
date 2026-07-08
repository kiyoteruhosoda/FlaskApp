"""Google OAuth / Google アカウント管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/routes.py`` の Google 関連エンドポイントを移植。
- ``POST /api/google/oauth/start`` — OAuth 認可 URL の生成
- ``GET  /api/google/accounts`` — 連携アカウント一覧
- ``PATCH /api/google/accounts/{account_id}`` — アカウント更新
- ``DELETE /api/google/accounts/{account_id}`` — アカウント削除
- ``POST /api/google/accounts/{account_id}/test`` — トークン疎通確認
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.crypto.crypto import decrypt
from shared.kernel.database.session import get_db
from shared.kernel.oauth_state_store import save_state
from shared.kernel.settings.settings import settings
from presentation.fastapi.dependencies.auth import get_current_principal

logger = logging.getLogger(__name__)

router = APIRouter(tags=["google"])

REQUIRED_GOOGLE_OAUTH_SCOPES = {
    "https://www.googleapis.com/auth/userinfo.email",
}


def _google_oauth_profile_scopes(scope_profile: str) -> set[str] | None:
    """名前付きスコーププロファイルを解決する。"""
    if scope_profile == "photo_picker":
        return set(settings.google_photo_picker_scopes)
    return None


def _build_callback_url(request: Request) -> str:
    """Google OAuth コールバック URL を構築する。

    設定 ``GOOGLE_OAUTH_REDIRECT_ORIGIN`` が有効な場合はそのオリジンを使い、
    そうでなければリクエストのスキーム・ホストを使う。
    コールバックパスは Flask の ``/auth/google/callback`` で固定。
    """
    configured = settings.google_oauth_redirect_origin
    if configured:
        from urllib.parse import urlsplit
        parts = urlsplit(configured)
        if parts.scheme in ("http", "https") and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}/auth/google/callback"

    # X-Forwarded-Proto / Forwarded ヘッダーからスキームを決定
    forwarded_proto = request.headers.get("X-Forwarded-Proto")
    if forwarded_proto:
        scheme = forwarded_proto.split(",")[0].strip().lower()
    else:
        forwarded = request.headers.get("Forwarded")
        scheme = None
        if forwarded:
            for part in forwarded.split(","):
                for attr in part.split(";"):
                    attr = attr.strip()
                    if attr.lower().startswith("proto="):
                        scheme = attr.split("=", 1)[1].strip().strip('"').lower()
                        break
                if scheme:
                    break
        if not scheme:
            scheme = request.url.scheme or "https"

    preferred = settings.preferred_url_scheme
    if preferred:
        scheme = str(preferred).strip().lower()

    host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or request.url.hostname
    return f"{scheme}://{host}/auth/google/callback"


@router.post("/google/oauth/start")
async def google_oauth_start(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """Google OAuth フローを開始して認可 URL を返す。"""
    if not settings.token_encryption_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "encryption_key_not_configured",
                "message": (
                    "Token encryption key (ENCRYPTION_KEY) is not configured. "
                    "Set it in System Settings > Security & Signing before "
                    "linking a Google account."
                ),
            },
        )

    body = await request.json() if await request.body() else {}
    scopes: set[str] = set(body.get("scopes") or [])
    scope_profile: Optional[str] = body.get("scope_profile")

    if scope_profile:
        profile_scopes = _google_oauth_profile_scopes(scope_profile)
        if profile_scopes is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_scope_profile", "scope_profile": scope_profile},
            )
        scopes.update(profile_scopes)

    scopes.update(REQUIRED_GOOGLE_OAUTH_SCOPES)
    sorted_scopes = sorted(scopes)
    redirect_target: Optional[str] = body.get("redirect")
    state_token = secrets.token_urlsafe(16)

    state_data = {
        "state": state_token,
        "scopes": sorted_scopes,
        "redirect": redirect_target,
        "user_id": principal.id,
    }
    # FastAPI で生成した state を Flask コールバックが参照できるよう共有ストアに保存
    save_state(state_token, state_data)

    callback_url = _build_callback_url(request)
    logger.info("OAuth start: user_id=%s", principal.id)

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": callback_url,
        "response_type": "code",
        "scope": " ".join(sorted_scopes),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state_token,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return {
        "auth_url": auth_url,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/google/accounts")
async def api_google_accounts(
    mine: int = Query(0, description="1 の場合は自分のアカウントのみ返す"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(200, ge=1, le=500),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """連携中の Google アカウント一覧を返す。"""
    from shared.infrastructure.models.google_account import GoogleAccount

    query = db.query(GoogleAccount)
    if mine:
        query = query.filter(GoogleAccount.user_id == principal.id)

    total = query.count()
    accounts = query.offset((page - 1) * pageSize).limit(pageSize).all()

    items = [
        {
            "id": acc.id,
            "email": acc.email,
            "status": acc.status,
            "scopes": acc.scopes_list(),
            "last_synced_at": (
                acc.last_synced_at.isoformat() if acc.last_synced_at else None
            ),
            "has_token": bool(acc.oauth_token_json),
        }
        for acc in accounts
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "pageSize": pageSize,
    }


@router.patch("/google/accounts/{account_id}")
async def api_google_account_update(
    account_id: int,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """Google アカウントのステータスを更新する。"""
    from shared.infrastructure.models.google_account import GoogleAccount

    account = db.get(GoogleAccount, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    body = await request.json()
    new_status = body.get("status")
    if new_status not in ("active", "disabled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_status"},
        )

    account.status = new_status
    db.commit()
    db.refresh(account)
    return {"result": "ok", "status": account.status}


@router.delete("/google/accounts/{account_id}")
async def api_google_account_delete(
    account_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """Google アカウントを削除してトークンを失効させる。"""
    from shared.infrastructure.models.google_account import GoogleAccount

    account = db.get(GoogleAccount, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    token_json = json.loads(decrypt(account.oauth_token_json) or "{}")
    refresh_token = token_json.get("refresh_token")
    if refresh_token:
        try:
            from shared.infrastructure.http_logging import log_requests_and_send
            log_requests_and_send(
                "POST",
                "https://oauth2.googleapis.com/revoke",
                data={"token": refresh_token},
                timeout=10,
            )
        except Exception:
            logger.warning(
                "Failed to revoke Google token for account_id=%s", account_id
            )

    db.delete(account)
    db.commit()
    return {"result": "deleted"}


@router.post("/google/accounts/{account_id}/test")
async def api_google_account_test(
    account_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """Google アカウントのトークンをテストする（アクセストークン再取得を試みる）。"""
    from shared.infrastructure.models.google_account import GoogleAccount
    from shared.infrastructure.google_oauth import RefreshTokenError, refresh_google_token

    account = db.get(GoogleAccount, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    try:
        refresh_google_token(account)
    except RefreshTokenError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": str(exc)},
        )

    return {"result": "ok"}


__all__ = ["router"]
