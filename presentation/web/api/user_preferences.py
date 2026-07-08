"""ユーザー設定 JSON API — `/api/user/preferences`."""
from __future__ import annotations

from flask import jsonify, request

from ..bootstrap.extensions import db
from shared.infrastructure.models.user import User
from shared.infrastructure.models.user_preference import UserPreference
from . import bp
from .routes import login_or_jwt_required, get_current_user

# 更新を許可するキーと各バリデーター {key: (type, validator_fn)}
_ALLOWED_KEYS: dict[str, tuple[type, object]] = {
    UserPreference.KEY_SLIDESHOW_INTERVAL: (int, lambda v: 1 <= v <= 300),
}


def _orm_user(user) -> User | None:
    return user if isinstance(user, User) else None


@bp.get("/user/preferences")
@login_or_jwt_required
def api_user_preferences_get():
    """現在のユーザーの設定を返す（未設定項目はデフォルト値で補完）。"""
    user = _orm_user(get_current_user())
    if user is None:
        return jsonify({"error": "authentication_required"}), 401

    prefs = UserPreference.get_all_for_user(user.id)
    return jsonify({"preferences": prefs})


@bp.put("/user/preferences")
@login_or_jwt_required
def api_user_preferences_update():
    """現在のユーザーの設定を更新する。

    Request body: ``{"slideshow_interval": 8}`` のように許可キーのみ送信。
    不明なキーは無視する。バリデーション失敗のキーはエラーを返す。
    """
    user = _orm_user(get_current_user())
    if user is None:
        return jsonify({"error": "authentication_required"}), 401

    payload = request.get_json(silent=True) or {}
    updated_keys: list[str] = []

    for key, raw_value in payload.items():
        if key not in _ALLOWED_KEYS:
            continue  # 未知キーは無視

        expected_type, validator = _ALLOWED_KEYS[key]
        # 型変換
        try:
            value = expected_type(raw_value)
        except (TypeError, ValueError):
            return (
                jsonify({
                    "error": "invalid_value",
                    "key": key,
                    "message": f"Value for '{key}' must be {expected_type.__name__}.",
                }),
                400,
            )
        # 値バリデーション
        if callable(validator) and not validator(value):
            return (
                jsonify({
                    "error": "value_out_of_range",
                    "key": key,
                    "message": f"Value for '{key}' is out of allowed range.",
                }),
                400,
            )
        UserPreference.set_for_user(user.id, key, value)
        updated_keys.append(key)

    if updated_keys:
        db.session.commit()

    prefs = UserPreference.get_all_for_user(user.id)
    return jsonify({"preferences": prefs, "updated": updated_keys})
