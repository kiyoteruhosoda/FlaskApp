"""TOTP 管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/routes_totp.py`` を移植。
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Callable

import pyotp
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

router = APIRouter(prefix="/totp", tags=["totp"])

_HASH_DIGESTS: dict[str, Callable] = {
    "sha1": hashlib.sha1,
    "sha256": hashlib.sha256,
    "sha512": hashlib.sha512,
}


def _ensure_totp_permission(principal: AuthenticatedPrincipal, perm_code: str) -> bool:
    return principal.can(perm_code)


def _resolve_digest(name: str | None) -> Callable:
    if not isinstance(name, str):
        return hashlib.sha1
    return _HASH_DIGESTS.get(name.strip().lower(), hashlib.sha1)


def _serialize_datetime(value) -> str | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_totp_uri(entity) -> str:
    digest = _resolve_digest(entity.algorithm)
    totp = pyotp.TOTP(entity.secret, digits=entity.digits, interval=entity.period, digest=digest)
    return totp.provisioning_uri(name=entity.account, issuer_name=entity.issuer)


def _generate_totp_preview(entity):
    digest = _resolve_digest(entity.algorithm)
    totp = pyotp.TOTP(entity.secret, digits=entity.digits, interval=entity.period, digest=digest)
    otp = totp.now()
    remaining = entity.period - int(time.time()) % entity.period
    if remaining <= 0:
        remaining = entity.period
    return otp, remaining


def _serialize_totp_entity(entity, preview=None) -> dict:
    if preview is None:
        otp, remaining = _generate_totp_preview(entity)
    else:
        otp, remaining = preview
    return {
        "id": entity.id,
        "account": entity.account,
        "issuer": entity.issuer,
        "secret": entity.secret,
        "description": entity.description,
        "algorithm": entity.algorithm,
        "digits": entity.digits,
        "period": entity.period,
        "created_at": _serialize_datetime(entity.created_at),
        "updated_at": _serialize_datetime(entity.updated_at),
        "otp": otp,
        "remaining_seconds": remaining,
        "otpauth_uri": _build_totp_uri(entity),
    }


def _coerce_optional_int(value, field: str) -> int | None:
    from bounded_contexts.totp.domain.exceptions import TOTPValidationError

    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise TOTPValidationError(f"{field} は数値で指定してください", field=field) from exc


def _resolve_totp_payload(payload: dict) -> dict:
    from bounded_contexts.totp.domain.parser import parse_otpauth_uri

    resolved: dict = {}
    otpauth_uri = (payload or {}).get("otpauth_uri")
    if otpauth_uri:
        parsed = parse_otpauth_uri(otpauth_uri)
        resolved.update({
            "account": parsed.account,
            "issuer": parsed.issuer,
            "secret": parsed.secret,
            "description": parsed.description,
            "algorithm": parsed.algorithm,
            "digits": parsed.digits,
            "period": parsed.period,
        })
    for key in ("account", "issuer", "secret", "description", "algorithm"):
        value = payload.get(key)
        if value not in (None, ""):
            resolved[key] = value
    digits_value = _coerce_optional_int(payload.get("digits"), "digits")
    if digits_value is not None:
        resolved["digits"] = digits_value
    period_value = _coerce_optional_int(payload.get("period"), "period")
    if period_value is not None:
        resolved["period"] = period_value
    return resolved


@router.get("")
async def api_totp_list(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """TOTP 一覧を返す。"""
    from bounded_contexts.totp.application.use_cases import TOTPListUseCase

    if not _ensure_totp_permission(principal, "totp:view"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})

    use_case = TOTPListUseCase()
    pairs = use_case.execute(user_id=int(principal.id))
    items = [
        _serialize_totp_entity(entity, (preview.otp, preview.remaining_seconds))
        for entity, preview in pairs
    ]
    return {"items": items}


@router.post("", status_code=status.HTTP_201_CREATED)
async def api_totp_create(
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """新しい TOTP を作成する。"""
    from bounded_contexts.totp.application.dto import TOTPCreateInput
    from bounded_contexts.totp.application.use_cases import TOTPCreateUseCase
    from bounded_contexts.totp.domain.exceptions import TOTPConflictError, TOTPValidationError

    if not _ensure_totp_permission(principal, "totp:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})

    resolved = _resolve_totp_payload(body)
    try:
        dto = TOTPCreateInput(
            account=resolved.get("account", ""),
            issuer=resolved.get("issuer", ""),
            secret=resolved.get("secret", ""),
            description=resolved.get("description", ""),
            digits=resolved.get("digits") or 6,
            period=resolved.get("period") or 30,
            algorithm=resolved.get("algorithm", "SHA1"),
            user_id=int(principal.id),
        )
        entity = TOTPCreateUseCase().execute(dto)
    except TOTPValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": "validation_error", "messages": [str(exc)]})
    except TOTPConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"error": "conflict", "message": str(exc)})

    return {"item": _serialize_totp_entity(entity)}


@router.get("/{totp_id}")
async def api_totp_get(
    totp_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """TOTP 詳細を返す。"""
    from bounded_contexts.totp.infrastructure.repositories import TOTPCredentialRepository
    from bounded_contexts.totp.domain.exceptions import TOTPNotFoundError

    if not _ensure_totp_permission(principal, "totp:view"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})

    try:
        repo = TOTPCredentialRepository()
        entity = repo.get(totp_id, user_id=int(principal.id))
    except TOTPNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    return {"item": _serialize_totp_entity(entity)}


@router.put("/{totp_id}")
async def api_totp_update(
    totp_id: int,
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """TOTP を更新する。"""
    from bounded_contexts.totp.application.dto import TOTPUpdateInput
    from bounded_contexts.totp.application.use_cases import TOTPUpdateUseCase
    from bounded_contexts.totp.domain.exceptions import TOTPNotFoundError, TOTPValidationError

    if not _ensure_totp_permission(principal, "totp:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})

    resolved = _resolve_totp_payload(body)
    try:
        dto = TOTPUpdateInput(
            id=totp_id,
            user_id=int(principal.id),
            account=resolved.get("account"),
            issuer=resolved.get("issuer"),
            secret=resolved.get("secret"),
            description=resolved.get("description"),
            digits=resolved.get("digits"),
            period=resolved.get("period"),
            algorithm=resolved.get("algorithm"),
        )
        entity = TOTPUpdateUseCase().execute(dto)
    except TOTPNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    except TOTPValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": "validation_error", "messages": [str(exc)]})

    return {"item": _serialize_totp_entity(entity)}


@router.delete("/{totp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_totp_delete(
    totp_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """TOTP を削除する。"""
    from bounded_contexts.totp.application.use_cases import TOTPDeleteUseCase
    from bounded_contexts.totp.domain.exceptions import TOTPNotFoundError

    if not _ensure_totp_permission(principal, "totp:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})

    try:
        TOTPDeleteUseCase().execute(totp_id=totp_id, user_id=int(principal.id))
    except TOTPNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})


@router.post("/export")
async def api_totp_export(
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """TOTP をエクスポートする。"""
    from bounded_contexts.totp.application.use_cases import TOTPExportUseCase

    if not _ensure_totp_permission(principal, "totp:export"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})

    ids = body.get("ids") or []
    result = TOTPExportUseCase().execute(user_id=int(principal.id), ids=ids)
    return {"export": result}


@router.post("/import")
async def api_totp_import(
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """TOTP をインポートする。"""
    from bounded_contexts.totp.application.dto import TOTPImportPayload, TOTPImportItem
    from bounded_contexts.totp.application.use_cases import TOTPImportUseCase
    from bounded_contexts.totp.domain.exceptions import TOTPValidationError

    if not _ensure_totp_permission(principal, "totp:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "forbidden"})

    items_raw = body.get("items") or []
    items = [TOTPImportItem(**item) for item in items_raw]
    payload = TOTPImportPayload(items=items, user_id=int(principal.id))

    try:
        result = TOTPImportUseCase().execute(payload)
    except TOTPValidationError as exc:
        raise HTTPException(status_code=400, detail={"error": "validation_error", "messages": [str(exc)]})

    return {"result": result}
