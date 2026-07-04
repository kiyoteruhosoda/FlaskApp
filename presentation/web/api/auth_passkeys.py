"""認証 JSON API — パスキー管理 (`/api/auth/passkeys`)."""
from __future__ import annotations

import json

from flask import current_app, jsonify, request, session

from ..bootstrap.extensions import db
from ..auth.routes import (
    PASSKEY_REGISTRATION_CHALLENGE_KEY,
    PASSKEY_REGISTRATION_USER_ID_KEY,
    _extract_passkey_credential_payload,
    _resolve_passkey_origin,
    _resolve_passkey_rp_id,
    passkey_service,
)
from shared.application.passkey_service import PasskeyRegistrationError
from shared.infrastructure.models.passkey import PasskeyCredential
from . import bp
from .routes import login_or_jwt_required, get_current_user
from shared.infrastructure.models.user import User


def _orm_user(user) -> User | None:
    return user if isinstance(user, User) else None


def _serialize_passkey(pk: PasskeyCredential) -> dict:
    return {
        "id": pk.id,
        "name": pk.name,
        "createdAt": pk.created_at.isoformat().replace("+00:00", "Z") if pk.created_at else None,
        "lastUsedAt": (
            pk.last_used_at.isoformat().replace("+00:00", "Z") if pk.last_used_at else None
        ),
        "transports": pk.transports or [],
    }


@bp.get("/auth/passkeys")
@login_or_jwt_required
def api_auth_passkeys_list():
    """現在のユーザーのパスキー一覧を返す。"""
    user = _orm_user(get_current_user())
    if user is None:
        return jsonify({"error": "not_supported"}), 403
    passkeys = (
        PasskeyCredential.query.filter_by(user_id=user.id)
        .order_by(PasskeyCredential.created_at.asc())
        .all()
    )
    return jsonify({"passkeys": [_serialize_passkey(pk) for pk in passkeys]})


@bp.delete("/auth/passkeys/<int:passkey_id>")
@login_or_jwt_required
def api_auth_passkey_delete(passkey_id: int):
    """指定パスキーを削除する。"""
    user = _orm_user(get_current_user())
    if user is None:
        return jsonify({"error": "not_supported"}), 403
    pk = db.session.get(PasskeyCredential, passkey_id)
    if pk is None or pk.user_id != user.id:
        return jsonify({"error": "not_found"}), 404
    db.session.delete(pk)
    db.session.commit()
    return jsonify({"result": "deleted", "id": passkey_id})


def _clear_registration_challenge():
    session.pop(PASSKEY_REGISTRATION_CHALLENGE_KEY, None)
    session.pop(PASSKEY_REGISTRATION_USER_ID_KEY, None)


@bp.get("/auth/passkey/options/register")
@login_or_jwt_required
def api_auth_passkey_register_options():
    """パスキー登録オプションを発行する（チャレンジはセッションに保持）。"""
    user = _orm_user(get_current_user())
    if user is None:
        return jsonify({"error": "not_supported"}), 403

    try:
        rp_id = _resolve_passkey_rp_id()
        options, challenge = passkey_service.generate_registration_options(
            user,
            rp_id=rp_id,
        )
    except Exception:
        current_app.logger.exception(
            "Failed to prepare passkey registration options",
            extra={"event": "api.auth.passkey_register", "path": request.path},
        )
        return jsonify({"error": "options_unavailable"}), 500

    session[PASSKEY_REGISTRATION_CHALLENGE_KEY] = challenge
    session[PASSKEY_REGISTRATION_USER_ID_KEY] = user.id
    session.modified = True
    return jsonify(options)


@bp.post("/auth/passkey/verify/register")
@login_or_jwt_required
def api_auth_passkey_verify_register():
    """パスキー登録レスポンスを検証して保存する。"""
    user = _orm_user(get_current_user())
    if user is None:
        _clear_registration_challenge()
        return jsonify({"error": "not_supported"}), 403

    challenge = session.get(PASSKEY_REGISTRATION_CHALLENGE_KEY)
    expected_user_id = session.get(PASSKEY_REGISTRATION_USER_ID_KEY)
    if not challenge or expected_user_id != user.id:
        _clear_registration_challenge()
        return jsonify({"error": "challenge_missing"}), 400

    payload = request.get_json(silent=True) or {}
    credential_payload = _extract_passkey_credential_payload(
        payload,
        meta_keys={"label", "name"},
        required_keys={"id", "rawId", "response"},
    )
    if not isinstance(credential_payload, dict):
        _clear_registration_challenge()
        return jsonify({"error": "invalid_payload"}), 400

    transports = None
    response_section = credential_payload.get("response")
    if isinstance(response_section, dict):
        transports = response_section.get("transports")

    label_raw = payload.get("label") or payload.get("name")
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
        _clear_registration_challenge()
        current_app.logger.warning(
            "Passkey registration verification failed",
            extra={
                "event": "api.auth.passkey_register",
                "path": request.path,
                "reason": exc.args[0] if exc.args else "verification_failed",
            },
        )
        return (
            jsonify({"error": exc.args[0] if exc.args else "verification_failed"}),
            400,
        )
    except Exception:
        _clear_registration_challenge()
        current_app.logger.exception(
            "Unexpected error during passkey registration",
            extra={"event": "api.auth.passkey_register", "path": request.path},
        )
        return jsonify({"error": "internal_error"}), 500

    _clear_registration_challenge()
    return jsonify({"result": "ok", "passkey": _serialize_passkey(record)})
