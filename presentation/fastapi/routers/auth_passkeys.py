"""パスキー管理 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/auth_passkeys.py`` を移植。

注意: パスキー登録チャレンジは Flask ではサーバーサイドセッションで管理していたが、
FastAPI 版では Redis/DB ベースのキャッシュへの移行が必要。
現版ではインメモリキャッシュ（シングルプロセス用）を使用する。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth:passkeys"])

# シングルプロセス用インメモリチャレンジキャッシュ
# 本番では Redis 等に移行すること
_challenge_cache: dict[int, bytes] = {}


def _serialize_passkey(pk) -> dict:
    return {
        "id": pk.id,
        "name": pk.name,
        "createdAt": pk.created_at.isoformat().replace("+00:00", "Z") if pk.created_at else None,
        "lastUsedAt": pk.last_used_at.isoformat().replace("+00:00", "Z") if pk.last_used_at else None,
        "transports": pk.transports or [],
    }


def _get_orm_user(principal: AuthenticatedPrincipal, db: Session):
    from shared.infrastructure.models.user import User

    user = db.get(User, int(principal.user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "authentication_required"},
        )
    return user


@router.get("/passkeys")
async def api_auth_passkeys_list(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """現在のユーザーのパスキー一覧を返す。"""
    from shared.infrastructure.models.passkey import PasskeyCredential

    user = _get_orm_user(principal, db)
    passkeys = (
        db.query(PasskeyCredential)
        .filter_by(user_id=user.id)
        .order_by(PasskeyCredential.created_at.asc())
        .all()
    )
    return {"passkeys": [_serialize_passkey(pk) for pk in passkeys]}


@router.delete("/passkeys/{passkey_id}")
async def api_auth_passkey_delete(
    passkey_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """指定パスキーを削除する。"""
    from shared.infrastructure.models.passkey import PasskeyCredential

    user = _get_orm_user(principal, db)
    pk = db.get(PasskeyCredential, passkey_id)
    if pk is None or pk.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})
    db.delete(pk)
    db.commit()
    return {"result": "deleted", "id": passkey_id}


@router.get("/passkey/options/register")
async def api_auth_passkey_register_options(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """パスキー登録オプションを発行する（チャレンジはインメモリキャッシュに保持）。"""
    from presentation.fastapi.auth.passkeys import (
        _resolve_passkey_rp_id,
        passkey_service,
    )

    user = _get_orm_user(principal, db)

    try:
        rp_id = _resolve_passkey_rp_id()
        options, challenge = passkey_service.generate_registration_options(user, rp_id=rp_id)
    except Exception:
        logger.exception("Failed to prepare passkey registration options")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "options_unavailable"},
        )

    _challenge_cache[user.id] = challenge
    return options


@router.post("/passkey/verify/register")
async def api_auth_passkey_verify_register(
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """パスキー登録レスポンスを検証して保存する。"""
    from shared.application.passkey_service import PasskeyRegistrationError
    from presentation.fastapi.auth.passkeys import (
        _extract_passkey_credential_payload,
        _resolve_passkey_origin,
        _resolve_passkey_rp_id,
        passkey_service,
    )

    user = _get_orm_user(principal, db)

    challenge = _challenge_cache.pop(user.id, None)
    if not challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "challenge_missing"},
        )

    credential_payload = _extract_passkey_credential_payload(
        body,
        meta_keys={"label", "name"},
        required_keys={"id", "rawId", "response"},
    )
    if not isinstance(credential_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_payload"},
        )

    transports = None
    response_section = credential_payload.get("response")
    if isinstance(response_section, dict):
        transports = response_section.get("transports")

    label_raw = body.get("label") or body.get("name")
    label = label_raw.strip() if isinstance(label_raw, str) and label_raw.strip() else None

    try:
        rp_id = _resolve_passkey_rp_id()
        origin = _resolve_passkey_origin()
        record = passkey_service.register_passkey(
            user=user,
            payload=json.dumps(credential_payload).encode("utf-8"),
            expected_challenge=challenge,
            transports=transports,
            name=label,
            expected_rp_id=rp_id,
            expected_origin=origin,
        )
    except PasskeyRegistrationError as exc:
        logger.warning("Passkey registration verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": exc.args[0] if exc.args else "verification_failed"},
        )
    except Exception:
        logger.exception("Unexpected error during passkey registration")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error"},
        )

    return {"result": "ok", "passkey": _serialize_passkey(record)}
