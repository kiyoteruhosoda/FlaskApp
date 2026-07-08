"""メンテナンス API（FastAPI）。

サービスアカウント JWT 認証 (``maintenance:read`` スコープ) が必要。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from shared.kernel.database.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


async def _require_maintenance_account(request: Request, db: Session = Depends(get_db)):
    """サービスアカウント JWT 認証で maintenance:read スコープを検証する。"""
    from presentation.fastapi.auth.service_account_auth import _verify_service_account_jwt

    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Authentication required."},
        )

    try:
        account = _verify_service_account_jwt(
            token,
            required_scopes=["maintenance:read"],
            audience=str(request.url).rstrip("/").rsplit("/api/maintenance", 1)[0] + "/api/maintenance",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Authentication required."},
        )

    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Authentication required."},
        )
    return account


@router.get("/ping")
async def maintenance_ping(account=Depends(_require_maintenance_account)):
    """メンテナンス API の疎通確認。"""
    return {"status": "ok", "service_account": account.name if account else None}
