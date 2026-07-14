"""サービスアカウント API キー管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/service_account_keys.py`` を移植。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/service_accounts", tags=["service-account-keys"])


def _parse_iso_datetime(raw: Any) -> datetime | None:
    if raw in (None, ""):
        return None
    if not isinstance(raw, str):
        raise ValueError("expires_at must be a string in ISO 8601 format")
    value = raw.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _has_manage_permission(principal: AuthenticatedPrincipal) -> bool:
    return principal.can("api_key:manage")


def _has_read_permission(principal: AuthenticatedPrincipal) -> bool:
    return _has_manage_permission(principal) or principal.can("api_key:read")


@router.get("/{account_id}/keys")
async def list_service_account_keys(
    account_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """サービスアカウントの API キー一覧を返す。"""
    from presentation.fastapi.services.service_account_api_key_service import (
        ServiceAccountApiKeyNotFoundError,
        ServiceAccountApiKeyService,
        ServiceAccountApiKeyValidationError,
    )

    if not _has_read_permission(principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})

    try:
        keys = ServiceAccountApiKeyService.list_keys(account_id)
    except ServiceAccountApiKeyValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.message})
    except ServiceAccountApiKeyNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    return {"items": [key.as_dict() for key in keys]}


@router.post("/{account_id}/keys", status_code=status.HTTP_201_CREATED)
async def create_service_account_key(
    account_id: int,
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """サービスアカウントの API キーを作成する。"""
    from presentation.fastapi.services.service_account_api_key_service import (
        ServiceAccountApiKeyNotFoundError,
        ServiceAccountApiKeyService,
        ServiceAccountApiKeyValidationError,
    )

    if not _has_manage_permission(principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})

    expires_at_raw = body.get("expires_at")
    try:
        expires_at = _parse_iso_datetime(expires_at_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "field": "expires_at"})

    try:
        record, api_key_value = ServiceAccountApiKeyService.create_key(
            account_id,
            scopes=body.get("scopes", ""),
            expires_at=expires_at,
            created_by=str(principal.id),
        )
    except ServiceAccountApiKeyValidationError as exc:
        response = {"error": exc.message}
        if exc.field:
            response["field"] = exc.field
        raise HTTPException(status_code=400, detail=response)
    except ServiceAccountApiKeyNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    result = record.as_dict()
    result["api_key"] = api_key_value
    return {"item": result}


@router.post("/{account_id}/keys/{key_id}/revoke")
async def revoke_service_account_key(
    account_id: int,
    key_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """API キーを無効化する。"""
    from presentation.fastapi.services.service_account_api_key_service import (
        ServiceAccountApiKeyNotFoundError,
        ServiceAccountApiKeyService,
        ServiceAccountApiKeyValidationError,
    )

    if not _has_manage_permission(principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})

    try:
        key = ServiceAccountApiKeyService.revoke_key(
            account_id, key_id, actor=str(principal.id)
        )
    except ServiceAccountApiKeyNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    except ServiceAccountApiKeyValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.message})

    return {"item": key.as_dict()}


@router.get("/{account_id}/keys/logs")
async def list_service_account_key_logs(
    account_id: int,
    key_id: int | None = Query(None),
    limit: int | None = Query(None),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """API キーのアクセスログを返す。"""
    from presentation.fastapi.services.service_account_api_key_service import (
        ServiceAccountApiKeyNotFoundError,
        ServiceAccountApiKeyService,
        ServiceAccountApiKeyValidationError,
    )

    if not _has_read_permission(principal):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})

    try:
        logs = ServiceAccountApiKeyService.list_logs(account_id, key_id=key_id, limit=limit)
    except ServiceAccountApiKeyValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": exc.message})
    except ServiceAccountApiKeyNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    return {"items": [log.as_dict() for log in logs]}
