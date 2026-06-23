"""認証 JSON API — パスキー管理 (`/api/auth/passkeys`)."""
from __future__ import annotations

from flask import jsonify

from ..bootstrap.extensions import db
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
