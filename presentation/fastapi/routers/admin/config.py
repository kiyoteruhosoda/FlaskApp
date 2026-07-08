"""管理者設定 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/admin_config.py`` を移植。
設定の永続化は既存の SystemSettingService を再利用する。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/config", tags=["admin:config"])


def _require_system_manage(principal: AuthenticatedPrincipal) -> None:
    if not principal.can("system:manage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "system:manage permission required"},
        )


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def _serialize_signing_groups(groups: list[dict]) -> list[dict]:
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


def _json_value_to_form_string(definition, value: Any) -> str:
    from presentation.fastapi.admin.system_settings_definitions import SettingFieldDefinition

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
    if value is None:
        return ""
    return str(value)


def _build_full_payload() -> dict:
    from presentation.fastapi.services.admin_config_service import (
        _build_config_context,
        _serialize_config_context,
        _list_server_signing_certificate_groups,
    )

    context = _build_config_context()
    payload = _serialize_config_context(context)
    payload["signingGroups"] = _serialize_signing_groups(
        context.get("server_signing_groups", [])
    )
    payload["status"] = "success"
    return payload


@router.get("", response_model=dict)
async def api_admin_config_get(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """アプリケーション設定の全体を返す。"""
    _require_system_manage(principal)
    try:
        return _build_full_payload()
    except Exception as exc:
        logger.exception("Failed to build config payload")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "config_load_failed", "message": str(exc)},
        )


@router.put("", response_model=dict)
async def api_admin_config_update(
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """アプリケーション設定を更新する。"""
    from presentation.fastapi.services.admin_config_service import (
        _build_config_context,
        _serialize_config_context,
        _parse_setting_value,
        _detect_relogin_changes,
        _HIDDEN_APPLICATION_SETTING_KEYS,
    )
    from presentation.fastapi.admin.system_settings_definitions import APPLICATION_SETTING_DEFINITIONS
    from presentation.fastapi.services.system_setting_service import SystemSettingService

    _require_system_manage(principal)

    updates_in = body.get("updates") or {}
    reset_keys_in = body.get("resetKeys") or []

    if not isinstance(updates_in, dict) or not isinstance(reset_keys_in, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_body", "message": "updates must be object, resetKeys must be array"},
        )
    if not updates_in and not reset_keys_in:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "no_changes", "message": "No updates or resets provided"},
        )

    context = _build_config_context()
    previous_config = dict(context["application_config"])

    errors: list[str] = []
    updates: dict[str, Any] = {}
    remove_keys: list[str] = []

    for key in reset_keys_in:
        definition = APPLICATION_SETTING_DEFINITIONS.get(key)
        if definition is None:
            errors.append(f"Unknown application setting: {key}")
            continue
        if not definition.editable:
            errors.append(f"{definition.label or key} is read-only and cannot be modified.")
            continue
        remove_keys.append(key)

    for key, raw_value in updates_in.items():
        if key in reset_keys_in:
            continue
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "validation_error", "messages": errors},
        )

    try:
        SystemSettingService.update_application_settings(updates, remove_keys=remove_keys)
    except Exception as exc:
        logger.exception("Failed to update application settings via API")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "update_failed", "message": "Failed to persist settings"},
        )

    payload = _build_full_payload()
    warnings = _detect_relogin_changes(
        previous_config,
        _build_config_context()["application_config"],
        APPLICATION_SETTING_DEFINITIONS,
    )
    if warnings:
        payload["warnings"] = warnings
    payload["updated"] = True
    return payload


@router.put("/cors", response_model=dict)
async def api_admin_config_cors_update(
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """CORS 許可オリジンを更新する。"""
    from presentation.fastapi.services.admin_config_service import _parse_setting_value
    from presentation.fastapi.admin.system_settings_definitions import CORS_SETTING_DEFINITIONS
    from presentation.fastapi.services.system_setting_service import SystemSettingService

    _require_system_manage(principal)

    updates: dict[str, Any] = {}
    remove_keys: list[str] = []

    if body.get("reset"):
        remove_keys.append("allowedOrigins")
    else:
        origins = body.get("allowedOrigins")
        if not isinstance(origins, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_body", "message": "allowedOrigins must be an array"},
            )
        definition = CORS_SETTING_DEFINITIONS.get("allowedOrigins")
        form_string = _json_value_to_form_string(definition, origins)
        try:
            parsed = _parse_setting_value("allowedOrigins", definition, form_string)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "validation_error", "messages": [str(exc)]},
            )
        invalid = [o for o in parsed if o != "*" and "://" not in o]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "validation_error",
                    "messages": [
                        f"Each origin must be a full URL or '*'. Invalid: {', '.join(invalid)}"
                    ],
                },
            )
        updates["allowedOrigins"] = parsed

    try:
        SystemSettingService.update_cors_settings(updates, remove_keys=remove_keys)
    except Exception:
        logger.exception("Failed to update CORS settings via API")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "update_failed", "message": "Failed to persist CORS settings"},
        )

    payload = _build_full_payload()
    payload["updated"] = True
    return payload


@router.put("/signing", response_model=dict)
async def api_admin_config_signing_update(
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """アクセストークンの署名方式を更新する。"""
    from presentation.fastapi.services.system_setting_service import (
        SystemSettingService,
        AccessTokenSigningValidationError,
    )

    _require_system_manage(principal)

    mode = (body.get("mode") or "").strip()

    if mode == "builtin":
        secret = (body.get("secret") or "").strip()
        if not secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "validation_error", "messages": ["A JWT secret key is required for built-in signing."]},
            )
        try:
            SystemSettingService.update_application_settings({"JWT_SECRET_KEY": secret})
            SystemSettingService.update_access_token_signing_setting("builtin")
        except AccessTokenSigningValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "validation_error", "messages": [str(exc)]},
            )
        except Exception:
            logger.exception("Failed to update built-in signing via API")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "update_failed", "message": "Failed to update signing configuration"},
            )
    elif mode == "server_signing":
        group_code = (body.get("groupCode") or "").strip()
        if not group_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "validation_error", "messages": ["Please select a certificate group for signing."]},
            )
        try:
            SystemSettingService.update_access_token_signing_setting("server_signing", group_code=group_code)
        except AccessTokenSigningValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "validation_error", "messages": [str(exc)]},
            )
        except Exception:
            logger.exception("Failed to update server signing via API")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "update_failed", "message": "Failed to update signing configuration"},
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "validation_error", "messages": ["Unsupported signing mode."]},
        )

    payload = _build_full_payload()
    payload["updated"] = True
    return payload
