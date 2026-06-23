"""管理 JSON API — アプリケーション設定 (/admin/config の React 化用)。

既存の ``presentation.web.admin.routes`` が持つ設定定義・検証・永続化ロジックを
再利用し、React から扱いやすいクリーンな JSON エンドポイントを提供する。
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from flask import current_app, jsonify, request

from . import bp
from .routes import login_or_jwt_required, get_current_user

from presentation.web.admin.routes import (
    _build_config_context,
    _serialize_config_context,
    _parse_setting_value,
    _detect_relogin_changes,
    _list_server_signing_certificate_groups,
    _HIDDEN_APPLICATION_SETTING_KEYS,
)
from presentation.web.admin.system_settings_definitions import (
    APPLICATION_SETTING_DEFINITIONS,
    CORS_SETTING_DEFINITIONS,
    SettingFieldDefinition,
)
from presentation.web.services.system_setting_service import (
    SystemSettingService,
    AccessTokenSigningSetting,
    AccessTokenSigningValidationError,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _require_system_manage():
    user = get_current_user()
    if user is None or not user.can("system:manage"):
        return jsonify(
            {"error": "forbidden", "message": "system:manage permission required"}
        ), 403
    return None


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def _serialize_signing_groups(groups: list[dict]) -> list[dict]:
    """証明書グループ一覧を JSON 化（datetime を ISO 文字列へ）。"""
    serialized: list[dict] = []
    for group in groups:
        latest = group.get("latest_certificate")
        latest_payload = None
        if latest:
            latest_payload = {
                "kid": latest.get("kid"),
                "issuedAt": _isoformat(latest.get("issued_at")),
                "expiresAt": _isoformat(latest.get("expires_at")),
                "algorithm": latest.get("algorithm"),
                "subject": latest.get("subject"),
            }
        serialized.append(
            {
                "groupCode": group.get("group_code"),
                "groupLabel": group.get("group_label"),
                "latestCertificate": latest_payload,
            }
        )
    return serialized


def _json_value_to_form_string(definition: SettingFieldDefinition, value: Any) -> str:
    """React から送られた型付き値を、既存 ``_parse_setting_value`` が解釈できる
    フォーム文字列表現へ変換する。"""
    if definition.data_type == "boolean":
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value).strip().lower()
    if definition.data_type in ("integer", "float"):
        if value is None:
            return ""
        return str(value).strip()
    if definition.data_type == "list":
        if isinstance(value, (list, tuple)):
            return "\n".join(str(item) for item in value)
        if value is None:
            return ""
        return str(value)
    # string
    if value is None:
        return ""
    return str(value)


def _full_payload() -> dict:
    """GET 用の完全なシリアライズ済み設定ペイロードを構築する。"""
    context = _build_config_context()
    payload = _serialize_config_context(context)
    payload["signingGroups"] = _serialize_signing_groups(
        context.get("server_signing_groups", [])
    )
    payload["status"] = "success"
    return payload


# ---------------------------------------------------------------------------
# GET /api/admin/config
# ---------------------------------------------------------------------------


@bp.get("/admin/config")
@login_or_jwt_required
def api_admin_config_get():
    """アプリケーション設定の全体を返す（セクション・フィールド・CORS・署名）。"""
    err = _require_system_manage()
    if err:
        return err
    return jsonify(_full_payload())


# ---------------------------------------------------------------------------
# PUT /api/admin/config  — アプリケーション設定の更新
# ---------------------------------------------------------------------------


@bp.put("/admin/config")
@login_or_jwt_required
def api_admin_config_update():
    """アプリケーション設定を更新する。

    Body: ``{ "updates": {key: typedValue}, "resetKeys": [key, ...] }``
    ``updates`` は値を保存、``resetKeys`` は既定値へ戻す（保存値を削除）。
    """
    err = _require_system_manage()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    updates_in = body.get("updates") or {}
    reset_keys_in = body.get("resetKeys") or []

    if not isinstance(updates_in, dict) or not isinstance(reset_keys_in, list):
        return jsonify({"error": "invalid_body", "message": "updates must be object, resetKeys must be array"}), 400

    if not updates_in and not reset_keys_in:
        return jsonify({"error": "no_changes", "message": "No updates or resets provided"}), 400

    context = _build_config_context()
    previous_config = dict(context["application_config"])

    errors: list[str] = []
    updates: dict[str, Any] = {}
    remove_keys: list[str] = []

    # reset to default
    for key in reset_keys_in:
        definition = APPLICATION_SETTING_DEFINITIONS.get(key)
        if definition is None:
            errors.append(f"Unknown application setting: {key}")
            continue
        if not definition.editable:
            errors.append(f"{definition.label or key} is read-only and cannot be modified.")
            continue
        remove_keys.append(key)

    # updates
    for key, raw_value in updates_in.items():
        if key in reset_keys_in:
            continue  # reset takes precedence
        if key in _HIDDEN_APPLICATION_SETTING_KEYS:
            errors.append(f"{key} cannot be modified through this endpoint.")
            continue
        definition = APPLICATION_SETTING_DEFINITIONS.get(key)
        if definition is None:
            errors.append(f"Unknown application setting: {key}")
            continue
        if not definition.editable:
            errors.append(f"{definition.label or key} is read-only and cannot be modified.")
            continue
        form_string = _json_value_to_form_string(definition, raw_value)
        try:
            parsed = _parse_setting_value(key, definition, form_string)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        updates[key] = parsed

    if errors:
        return jsonify({"error": "validation_error", "messages": errors}), 400

    try:
        SystemSettingService.update_application_settings(updates, remove_keys=remove_keys)
        from presentation.web import _apply_persisted_settings

        _apply_persisted_settings(current_app)
    except Exception:  # pragma: no cover - defensive
        from shared.kernel.database.db import db

        db.session.rollback()
        current_app.logger.exception("Failed to update application settings via API")
        return jsonify({"error": "update_failed", "message": "Failed to persist settings"}), 500

    payload = _full_payload()
    warnings = _detect_relogin_changes(
        previous_config,
        _build_config_context()["application_config"],
        APPLICATION_SETTING_DEFINITIONS,
    )
    if warnings:
        payload["warnings"] = warnings
    payload["updated"] = True
    return jsonify(payload)


# ---------------------------------------------------------------------------
# PUT /api/admin/config/cors  — CORS 許可オリジンの更新
# ---------------------------------------------------------------------------


@bp.put("/admin/config/cors")
@login_or_jwt_required
def api_admin_config_cors_update():
    """CORS 許可オリジンを更新する。

    Body: ``{ "allowedOrigins": [...] }`` または ``{ "reset": true }``。
    """
    err = _require_system_manage()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    definition = CORS_SETTING_DEFINITIONS.get("allowedOrigins")

    updates: dict[str, Any] = {}
    remove_keys: list[str] = []

    if body.get("reset"):
        remove_keys.append("allowedOrigins")
    else:
        origins = body.get("allowedOrigins")
        if not isinstance(origins, list):
            return jsonify({"error": "invalid_body", "message": "allowedOrigins must be an array"}), 400
        form_string = _json_value_to_form_string(definition, origins)
        try:
            parsed = _parse_setting_value("allowedOrigins", definition, form_string)
        except ValueError as exc:
            return jsonify({"error": "validation_error", "messages": [str(exc)]}), 400
        invalid = [o for o in parsed if o != "*" and "://" not in o]
        if invalid:
            return jsonify(
                {
                    "error": "validation_error",
                    "messages": [
                        f"Each origin must be a full URL (e.g., https://example.com) or '*'. Invalid: {', '.join(invalid)}"
                    ],
                }
            ), 400
        updates["allowedOrigins"] = parsed

    try:
        SystemSettingService.update_cors_settings(updates, remove_keys=remove_keys)
        from presentation.web import _apply_persisted_settings

        _apply_persisted_settings(current_app)
    except Exception:  # pragma: no cover - defensive
        from shared.kernel.database.db import db

        db.session.rollback()
        current_app.logger.exception("Failed to update CORS settings via API")
        return jsonify({"error": "update_failed", "message": "Failed to persist CORS settings"}), 500

    payload = _full_payload()
    payload["updated"] = True
    return jsonify(payload)


# ---------------------------------------------------------------------------
# PUT /api/admin/config/signing  — アクセストークン署名設定の更新
# ---------------------------------------------------------------------------


@bp.put("/admin/config/signing")
@login_or_jwt_required
def api_admin_config_signing_update():
    """アクセストークンの署名方式を更新する。

    Body: ``{ "mode": "builtin", "secret": "..." }`` または
    ``{ "mode": "server_signing", "groupCode": "..." }``。
    """
    err = _require_system_manage()
    if err:
        return err

    body = request.get_json(silent=True) or {}
    mode = (body.get("mode") or "").strip()

    if mode == "builtin":
        secret = (body.get("secret") or "").strip()
        if not secret:
            return jsonify({"error": "validation_error", "messages": ["A JWT secret key is required for built-in signing."]}), 400
        try:
            SystemSettingService.update_application_settings({"JWT_SECRET_KEY": secret})
            from presentation.web import _apply_persisted_settings

            _apply_persisted_settings(current_app)
            SystemSettingService.update_access_token_signing_setting("builtin")
        except AccessTokenSigningValidationError as exc:
            return jsonify({"error": "validation_error", "messages": [str(exc)]}), 400
        except Exception:  # pragma: no cover - defensive
            from shared.kernel.database.db import db

            db.session.rollback()
            current_app.logger.exception("Failed to update built-in signing via API")
            return jsonify({"error": "update_failed", "message": "Failed to update signing configuration"}), 500
    elif mode == "server_signing":
        group_code = (body.get("groupCode") or "").strip()
        if not group_code:
            return jsonify({"error": "validation_error", "messages": ["Please select a certificate group for signing."]}), 400
        try:
            SystemSettingService.update_access_token_signing_setting("server_signing", group_code=group_code)
        except AccessTokenSigningValidationError as exc:
            return jsonify({"error": "validation_error", "messages": [str(exc)]}), 400
        except Exception:  # pragma: no cover - defensive
            current_app.logger.exception("Failed to update server signing via API")
            return jsonify({"error": "update_failed", "message": "Failed to update signing configuration"}), 500
    else:
        return jsonify({"error": "validation_error", "messages": ["Unsupported signing mode."]}), 400

    payload = _full_payload()
    payload["updated"] = True
    return jsonify(payload)
