
import json
import os
import platform
import socket
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Dict, Mapping

import flask
from flask import (
    Blueprint,
    render_template,
    flash,
    redirect,
    url_for,
    request,
    jsonify,
    session,
    current_app,
)
from ..extensions import db
from flask_login import login_required, current_user
from flask_babel import gettext as _

from core.models.system_setting import SystemSetting
from core.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_CORS_SETTINGS,
)
from core.models.user import User, Role, Permission
from core.models.service_account import ServiceAccount
from core.settings import settings
from core.storage_service import StorageService
from domain.storage import StorageDomain
from webapp.services.service_account_service import (
    ServiceAccountNotFoundError,
    ServiceAccountService,
    ServiceAccountValidationError,
)
from webapp.services.service_account_api_key_service import (
    ServiceAccountApiKeyNotFoundError,
    ServiceAccountApiKeyService,
    ServiceAccountApiKeyValidationError,
)
from features.certs.application.services import default_certificate_services
from features.certs.application.use_cases import (
    GetCertificateGroupUseCase,
    ListCertificateGroupsUseCase,
    ListIssuedCertificatesUseCase,
)
from features.certs.domain.exceptions import (
    CertificateGroupNotFoundError,
    CertificatePrivateKeyNotFoundError,
)
from features.certs.domain.usage import UsageType
from webapp.admin.system_settings_definitions import (
    APPLICATION_SETTING_DEFINITIONS,
    APPLICATION_SETTING_SECTIONS,
    CORS_SETTING_DEFINITIONS,
    READONLY_APPLICATION_SETTING_KEYS,
    SettingFieldDefinition,
)


_HIDDEN_APPLICATION_SETTING_KEYS: frozenset[str] = frozenset({"JWT_SECRET_KEY"})
from webapp.services.system_setting_service import (
    AccessTokenSigningSetting,
    AccessTokenSigningValidationError,
    SystemSettingService,
)


bp = Blueprint("admin", __name__, template_folder="templates")


_RELOGIN_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "SECRET_KEY",
        "SESSION_COOKIE_SECURE",
        "SESSION_COOKIE_HTTPONLY",
        "SESSION_COOKIE_SAMESITE",
        "PERMANENT_SESSION_LIFETIME",
    }
)



# --- ここから各ルート定義 ---


# Permission helpers -----------------------------------------------------


def _can_manage_api_keys() -> bool:
    if not hasattr(current_user, "can"):
        return False
    return current_user.can("api_key:manage")


def _can_read_api_keys() -> bool:
    if not hasattr(current_user, "can"):
        return False
    if _can_manage_api_keys():
        return True
    return current_user.can("api_key:read")


def _infer_data_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (list, tuple)):
        return "list"
    return "string"


def _build_custom_definition(key: str, sample: Any | None) -> SettingFieldDefinition:
    data_type = _infer_data_type(sample)
    return SettingFieldDefinition(
        key=key,
        label=key,
        data_type=data_type,
        required=False,
        description=_(u"Custom application setting."),
        allow_empty=True,
        allow_null=True,
        multiline=data_type == "list",
    )


def _collect_application_definitions(
    effective_config: Dict[str, Any],
    stored_payload: Dict[str, Any],
) -> Dict[str, SettingFieldDefinition]:
    definitions: Dict[str, SettingFieldDefinition] = dict(APPLICATION_SETTING_DEFINITIONS)
    keys = (
        set(DEFAULT_APPLICATION_SETTINGS)
        | set(effective_config)
        | set(stored_payload)
    ) - set(_HIDDEN_APPLICATION_SETTING_KEYS)
    for key in keys:
        if key not in definitions:
            sample = stored_payload.get(key, effective_config.get(key))
            definitions[key] = _build_custom_definition(key, sample)
    return definitions


def _detect_relogin_changes(
    previous_config: Dict[str, Any],
    current_config: Dict[str, Any],
    definitions: Dict[str, SettingFieldDefinition],
) -> list[str]:
    messages: list[str] = []
    for key in sorted(_RELOGIN_REQUIRED_KEYS):
        if previous_config.get(key) == current_config.get(key):
            continue
        definition = definitions.get(key)
        label = definition.label if definition and definition.label else key
        messages.append(
            _(u"Changes to %(setting)s require all users to sign in again.", setting=label)
        )
    return messages


def _format_value_for_display(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _compose_search_text(*parts: Any) -> str:
    tokens: list[str] = []
    for part in parts:
        if not part:
            continue
        if isinstance(part, (list, tuple, set)):
            tokens.append(_compose_search_text(*part))
        else:
            tokens.append(str(part))
    return " ".join(token.strip() for token in tokens if token).lower()


def _normalise_allowed_origins(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        candidates = value
    else:
        candidates = [value]
    normalised: list[str] = []
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).strip()
        if not text:
            continue
        normalised.append(text)
    return normalised


def _value_to_form_string(definition: SettingFieldDefinition, value: Any) -> str:
    if value is None:
        return ""
    if definition.data_type == "boolean":
        return "true" if bool(value) else "false"
    if definition.data_type in {"integer", "float"}:
        return str(value)
    if definition.data_type == "list":
        if isinstance(value, (list, tuple)):
            return "\n".join(str(item) for item in value)
        return str(value)
    return str(value)


def _build_setting_row(
    *,
    key: str,
    definition: SettingFieldDefinition,
    defaults: Mapping[str, Any],
    effective_config: Dict[str, Any],
    stored_payload: Dict[str, Any],
    override_values: Mapping[str, str],
    selected: set[str],
    default_flags: set[str],
) -> Dict[str, Any]:
    current_value = effective_config.get(key)
    stored_has_value = key in stored_payload
    stored_value = stored_payload.get(key)
    default_value = defaults.get(key)

    if key in override_values:
        form_value = override_values[key]
    elif stored_has_value:
        form_value = _value_to_form_string(definition, stored_value)
    else:
        form_value = _value_to_form_string(definition, current_value)

    current_json = _format_value_for_display(current_value)
    default_json = _format_value_for_display(default_value) if key in defaults else ""
    choices = definition.choice_labels()
    choices_text = " ".join(
        f"{value} {label}" for value, label in choices
    )

    search_text = _compose_search_text(
        key,
        definition.label,
        definition.description,
        current_json,
        default_json,
        form_value,
        definition.default_hint or "",
        choices_text,
    )

    return {
        "key": key,
        "label": definition.label,
        "data_type": definition.data_type,
        "required": definition.required,
        "description": definition.description,
        "current_json": current_json,
        "default_json": default_json,
        "form_value": form_value,
        "choices": choices,
        "multiline": definition.multiline,
        "selected": key in selected,
        "use_default": key in default_flags,
        "using_default": not stored_has_value,
        "allow_empty": definition.allow_empty,
        "allow_null": definition.allow_null,
        "editable": definition.editable,
        "default_hint": definition.default_hint,
        "search_text": search_text,
    }


def _prepare_application_field_models(
    definitions: Dict[str, SettingFieldDefinition],
    effective_config: Dict[str, Any],
    stored_payload: Dict[str, Any],
    *,
    overrides: Dict[str, str] | None = None,
    selected_keys: set[str] | None = None,
    default_flags: set[str] | None = None,
) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    override_values = overrides or {}
    selected = selected_keys or set()
    defaults = default_flags or set()

    rows_by_key: dict[str, Dict[str, Any]] = {}
    for key in sorted(definitions):
        definition = definitions[key]
        rows_by_key[key] = _build_setting_row(
            key=key,
            definition=definition,
            defaults=DEFAULT_APPLICATION_SETTINGS,
            effective_config=effective_config,
            stored_payload=stored_payload,
            override_values=override_values,
            selected=selected,
            default_flags=defaults,
        )

    sections: list[Dict[str, Any]] = []
    flat_rows: list[Dict[str, Any]] = []
    used_keys: set[str] = set()

    for section in APPLICATION_SETTING_SECTIONS:
        section_rows: list[Dict[str, Any]] = []
        for definition in section.fields:
            row = rows_by_key.get(definition.key)
            if not row:
                continue
            enriched = {**row}
            enriched.update(
                {
                    "section": section.identifier,
                    "section_label": section.label,
                    "anchor_id": f"setting-{definition.key}",
                }
            )
            section_rows.append(enriched)
            flat_rows.append(enriched)
            used_keys.add(definition.key)
        if section_rows:
            sections.append(
                {
                    "identifier": section.identifier,
                    "label": section.label,
                    "description": section.description,
                    "fields": section_rows,
                    "anchor_id": f"section-{section.identifier}",
                    "search_text": _compose_search_text(
                        section.label,
                        section.description or "",
                        *(row["search_text"] for row in section_rows),
                    ),
                }
            )

    custom_keys = sorted(key for key in rows_by_key if key not in used_keys)
    if custom_keys:
        custom_label = _(u"Custom keys")
        custom_description = _(u"Settings without predefined metadata.")
        custom_rows: list[Dict[str, Any]] = []
        for key in custom_keys:
            row = rows_by_key[key]
            enriched = {**row}
            enriched.update(
                {
                    "section": "custom",
                    "section_label": custom_label,
                    "anchor_id": f"setting-{key}",
                }
            )
            custom_rows.append(enriched)
            flat_rows.append(enriched)
        sections.append(
            {
                "identifier": "custom",
                "label": custom_label,
                "description": custom_description,
                "fields": custom_rows,
                "anchor_id": "section-custom",
                "search_text": _compose_search_text(
                    custom_label,
                    custom_description,
                    *(row["search_text"] for row in custom_rows),
                ),
            }
        )

    return sections, flat_rows


def _collect_cors_definitions() -> Dict[str, SettingFieldDefinition]:
    return dict(CORS_SETTING_DEFINITIONS)


def _build_cors_field_rows(
    definitions: Dict[str, SettingFieldDefinition],
    effective_config: Dict[str, Any],
    stored_payload: Dict[str, Any],
    *,
    overrides: Dict[str, str] | None = None,
    selected_keys: set[str] | None = None,
    default_flags: set[str] | None = None,
) -> list[Dict[str, Any]]:
    override_values = overrides or {}
    selected = selected_keys or set()
    defaults = default_flags or set()
    rows: list[Dict[str, Any]] = []

    for key in sorted(definitions):
        definition = definitions[key]
        rows.append(
            _build_setting_row(
                key=key,
                definition=definition,
                defaults=DEFAULT_CORS_SETTINGS,
                effective_config=effective_config,
                stored_payload=stored_payload,
                override_values=override_values,
                selected=selected,
                default_flags=defaults,
            )
        )

    return rows


def _build_config_context(
    *,
    app_overrides: Dict[str, str] | None = None,
    app_selected: set[str] | None = None,
    app_use_defaults: set[str] | None = None,
    cors_overrides: Dict[str, str] | None = None,
    cors_use_defaults: set[str] | None = None,
    builtin_signing_secret: str | None = None,
) -> Dict[str, Any]:
    application_payload = SystemSettingService.load_application_config_payload()
    application_config = {**DEFAULT_APPLICATION_SETTINGS, **application_payload}

    readonly_application_values: dict[str, Any] = {}
    for key in READONLY_APPLICATION_SETTING_KEYS:
        if key in readonly_application_values:
            continue
        readonly_application_values[key] = current_app.config.get(key)
    application_config = {**readonly_application_values, **application_config}
    cors_payload = SystemSettingService.load_cors_config_payload()
    cors_config = {**DEFAULT_CORS_SETTINGS, **cors_payload}
    effective_allowed_origins = _normalise_allowed_origins(
        current_app.config.get("CORS_ALLOWED_ORIGINS")
    )
    cors_config["CORS_ALLOWED_ORIGINS"] = effective_allowed_origins
    cors_payload_for_rows = {**cors_payload, "CORS_ALLOWED_ORIGINS": effective_allowed_origins}

    application_definitions = _collect_application_definitions(application_config, application_payload)
    cors_definitions = _collect_cors_definitions()

    application_sections, application_fields = _prepare_application_field_models(
        application_definitions,
        application_config,
        application_payload,
        overrides=app_overrides,
        selected_keys=app_selected,
        default_flags=app_use_defaults,
    )
    cors_fields = _build_cors_field_rows(
        cors_definitions,
        cors_config,
        cors_payload_for_rows,
        overrides=cors_overrides,
        default_flags=cors_use_defaults,
    )

    try:
        signing_setting = SystemSettingService.get_access_token_signing_setting()
    except AccessTokenSigningValidationError as exc:
        flash(str(exc), "danger")
        signing_setting = AccessTokenSigningSetting(mode="server_signing")

    certificate_groups = _list_server_signing_certificate_groups()

    app_setting_record = SystemSetting.query.filter_by(setting_key="app.config").one_or_none()
    cors_setting_record = SystemSetting.query.filter_by(setting_key="app.cors").one_or_none()
    signing_record = SystemSetting.query.filter_by(setting_key="access_token_signing").one_or_none()

    builtin_secret_value = (
        builtin_signing_secret
        if builtin_signing_secret is not None
        else application_config.get("JWT_SECRET_KEY")
    )

    return {
        "application_payload": application_payload,
        "application_config": application_config,
        "cors_payload": cors_payload,
        "cors_config": cors_config,
        "application_definitions": application_definitions,
        "cors_definitions": cors_definitions,
        "application_sections": application_sections,
        "application_fields": application_fields,
        "cors_fields": cors_fields,
        "signing_setting": signing_setting,
        "server_signing_groups": certificate_groups,
        "application_config_updated_at": getattr(app_setting_record, "updated_at", None),
        "application_config_description": getattr(app_setting_record, "description", None),
        "cors_config_updated_at": getattr(cors_setting_record, "updated_at", None),
        "cors_config_description": getattr(cors_setting_record, "description", None),
        "signing_config_updated_at": getattr(signing_record, "updated_at", None),
        "builtin_signing_secret": builtin_secret_value,
    }


def _serialize_config_context(context: Dict[str, Any]) -> Dict[str, Any]:
    from dataclasses import asdict

    def _isoformat(value: Any) -> str | None:
        if value is None:
            return None
        try:
            return value.isoformat()
        except AttributeError:
            return str(value)

    serialized = {
        "application_sections": context.get("application_sections", []),
        "application_fields": context.get("application_fields", []),
        "cors_fields": context.get("cors_fields", []),
        "cors_effective_origins": context.get("cors_config", {}).get("CORS_ALLOWED_ORIGINS", []),
        "signing_setting": asdict(context["signing_setting"]) if context.get("signing_setting") else None,
        "builtin_signing_secret": context.get("builtin_signing_secret"),
        "timestamps": {
            "application_config_updated_at": _isoformat(context.get("application_config_updated_at")),
            "cors_config_updated_at": _isoformat(context.get("cors_config_updated_at")),
            "signing_config_updated_at": _isoformat(context.get("signing_config_updated_at")),
        },
        "descriptions": {
            "application_config_description": context.get("application_config_description"),
            "cors_config_description": context.get("cors_config_description"),
        },
    }

    return serialized


def _parse_setting_value(key: str, definition: SettingFieldDefinition, raw_value: str | None):
    label = definition.label or key
    if definition.data_type == "boolean":
        if raw_value not in {"true", "false"}:
            raise ValueError(
                _(u"Please choose a value for %(key)s.", key=label)
            )
        return raw_value == "true"

    if definition.data_type == "integer":
        if raw_value is None or not raw_value.strip():
            raise ValueError(_(u"Value for %(key)s is required.", key=label))
        try:
            return int(raw_value.strip())
        except ValueError:
            raise ValueError(_(u"Value for %(key)s must be an integer.", key=label)) from None

    if definition.data_type == "float":
        if raw_value is None or not raw_value.strip():
            raise ValueError(_(u"Value for %(key)s is required.", key=label))
        try:
            return float(raw_value.strip())
        except ValueError:
            raise ValueError(_(u"Value for %(key)s must be a number.", key=label)) from None

    if definition.data_type == "list":
        normalized = []
        if raw_value:
            for line in raw_value.splitlines():
                item = line.strip()
                if item:
                    normalized.append(item)
        if not normalized and definition.required and not definition.allow_empty:
            raise ValueError(_(u"Value for %(key)s cannot be empty.", key=label))
        return normalized

    # String-like fields
    if raw_value is None:
        raw_value = ""
    value = raw_value.strip()
    if not value:
        if definition.allow_empty:
            return ""
        if definition.allow_null:
            return None
        raise ValueError(_(u"Value for %(key)s is required.", key=label))
    return value


# サービスアカウント管理
@bp.route("/service-accounts")
@login_required
def service_accounts():
    can_manage_accounts = current_user.can("service_account:manage")
    can_access_api_keys = _can_read_api_keys()

    if not (can_manage_accounts or can_access_api_keys):
        return _(u"You do not have permission to access this page."), 403

    accounts = [account.as_dict() for account in ServiceAccountService.list_accounts()]
    certificate_groups = [
        {
            "group_code": group.group_code,
            "display_name": group.display_name,
            "usage_type": group.usage_type.value,
        }
        for group in ListCertificateGroupsUseCase().execute()
        if group.usage_type == UsageType.CLIENT_SIGNING
    ]
    certificate_groups.sort(key=lambda item: item["display_name"] or item["group_code"])
    available_scopes = (
        sorted(current_user.permissions) if can_manage_accounts else []
    )
    return render_template(
        "admin/service_accounts.html",
        accounts=accounts,
        available_scopes=available_scopes,
        can_manage_accounts=can_manage_accounts,
        can_access_api_keys=can_access_api_keys,
        certificate_groups=certificate_groups,
    )


@bp.route("/service-accounts.json", methods=["GET"])
@login_required
def service_accounts_json():
    if not current_user.can("service_account:manage"):
        return jsonify({"error": "forbidden"}), 403

    accounts = [account.as_dict() for account in ServiceAccountService.list_accounts()]
    return jsonify({"items": accounts})


@bp.route("/service-accounts.json", methods=["POST"])
@login_required
def service_accounts_create():
    if not current_user.can("service_account:manage"):
        return jsonify({"error": "forbidden"}), 403

    payload = _extract_service_account_payload()
    try:
        account = ServiceAccountService.create_account(
            name=payload.get("name", ""),
            description=payload.get("description"),
            certificate_group_code=payload.get("certificate_group_code", ""),
            scope_names=payload.get("scope_names", ""),
            active=payload.get("active_flg", True),
            allowed_scopes=current_user.permissions,
        )
    except ServiceAccountValidationError as exc:
        response = {"error": exc.message}
        if exc.field:
            response["field"] = exc.field
        return jsonify(response), 400

    return jsonify({"item": account.as_dict()}), 201


@bp.route("/service-accounts/<int:account_id>.json", methods=["GET"])
@login_required
def service_accounts_detail(account_id: int):
    if not current_user.can("service_account:manage"):
        return jsonify({"error": "forbidden"}), 403

    account = ServiceAccount.query.get(account_id)
    if not account:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"item": account.as_dict()})


@bp.route("/service-accounts/<int:account_id>.json", methods=["PUT", "PATCH"])
@login_required
def service_accounts_update(account_id: int):
    if not current_user.can("service_account:manage"):
        return jsonify({"error": "forbidden"}), 403

    payload = _extract_service_account_payload()
    try:
        account = ServiceAccountService.update_account(
            account_id,
            name=payload.get("name", ""),
            description=payload.get("description"),
            certificate_group_code=payload.get("certificate_group_code", ""),
            scope_names=payload.get("scope_names", ""),
            active=payload.get("active_flg", True),
            allowed_scopes=current_user.permissions,
        )
    except ServiceAccountNotFoundError:
        return jsonify({"error": "not_found"}), 404
    except ServiceAccountValidationError as exc:
        response = {"error": exc.message}
        if exc.field:
            response["field"] = exc.field
        return jsonify(response), 400

    return jsonify({"item": account.as_dict()})


@bp.route("/service-accounts/<int:account_id>.json", methods=["DELETE"])
@login_required
def service_accounts_delete(account_id: int):
    if not current_user.can("service_account:manage"):
        return jsonify({"error": "forbidden"}), 403

    try:
        ServiceAccountService.delete_account(account_id)
    except ServiceAccountNotFoundError:
        return jsonify({"error": "not_found"}), 404

    return jsonify({"status": "deleted"}), 200


@bp.route("/service-accounts/<int:account_id>/api-keys")
@login_required
def service_account_api_keys(account_id: int):
    if not _can_read_api_keys():
        return _(u"You do not have permission to access this page."), 403

    account = ServiceAccount.query.get(account_id)
    if not account:
        flash(_(u"The requested service account could not be found."), "warning")
        return redirect(url_for("admin.service_accounts"))

    try:
        key_records = ServiceAccountApiKeyService.list_keys(account_id)
    except ServiceAccountApiKeyNotFoundError:
        flash(_(u"The requested service account could not be found."), "warning")
        return redirect(url_for("admin.service_accounts"))
    except ServiceAccountApiKeyValidationError as exc:
        flash(exc.message, "danger")
        key_records = []

    account_dict = account.as_dict()
    account_dict["scopes"] = account.scopes
    account_dict["active"] = account.is_active()
    if account.certificate_group_code:
        try:
            group = GetCertificateGroupUseCase().execute(account.certificate_group_code)
            account_dict["certificate_group_display_name"] = group.display_name
        except CertificateGroupNotFoundError:
            account_dict["certificate_group_display_name"] = None
    else:
        account_dict["certificate_group_display_name"] = None

    return render_template(
        "admin/service_account_api_keys.html",
        account=account_dict,
        initial_keys=[record.as_dict() for record in key_records],
        can_manage_api_keys=_can_manage_api_keys(),
    )


# Config表示ページ（管理者のみ）
@bp.route("/config", methods=["GET", "POST"])
@login_required
def show_config():
    if not current_user.can("system:manage"):
        return _(u"You do not have permission to access this page."), 403
    wants_json = request.accept_mimetypes["application/json"] > request.accept_mimetypes["text/html"]
    is_ajax = wants_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"

    app_overrides: Dict[str, str] = {}
    app_selected: set[str] = set()
    app_use_defaults: set[str] = set()
    cors_overrides: Dict[str, str] = {}
    cors_use_defaults: set[str] = set()
    relogin_previous_config: Dict[str, Any] | None = None
    builtin_secret_override: str | None = None

    context = _build_config_context()
    application_definitions = context["application_definitions"]
    cors_definitions = context["cors_definitions"]

    if request.method == "POST":
        action = (request.form.get("action") or "update-signing").strip()
        errors: list[str] = []
        warnings: list[str] = []
        success_message: str | None = None

        if action == "update-signing":
            selected = (request.form.get("access_token_signing") or "builtin").strip()
            raw_secret_input = request.form.get("builtin_secret")
            if raw_secret_input is not None:
                builtin_secret_override = raw_secret_input.strip()
            if selected == "builtin":
                secret_value = builtin_secret_override or ""
                if not secret_value:
                    errors.append(_(u"Please provide a JWT secret key for built-in signing."))
                else:
                    try:
                        SystemSettingService.update_application_settings(
                            {"JWT_SECRET_KEY": secret_value}
                        )
                        from webapp import _apply_persisted_settings

                        _apply_persisted_settings(current_app)
                    except Exception:  # pragma: no cover - unexpected failure logged for debugging
                        db.session.rollback()
                        current_app.logger.exception(
                            "Failed to persist built-in JWT signing secret"
                        )
                        errors.append(_(u"Failed to update the built-in signing secret."))
                    else:
                        try:
                            SystemSettingService.update_access_token_signing_setting("builtin")
                            success_message = _(
                                u"Access token signing will use the built-in secret."
                            )
                        except AccessTokenSigningValidationError as exc:
                            errors.append(str(exc))
                        except Exception:  # pragma: no cover - unexpected failure logged for debugging
                            current_app.logger.exception(
                                "Failed to update access token signing configuration"
                            )
                            errors.append(
                                _(u"Failed to update the access token signing configuration.")
                            )
            else:
                try:
                    prefix = "server_signing:"
                    group_code = selected[len(prefix):] if selected.startswith(prefix) else selected
                    SystemSettingService.update_access_token_signing_setting(
                        "server_signing", group_code=group_code
                    )
                    success_message = _(u"Access token signing certificate group updated.")
                except AccessTokenSigningValidationError as exc:
                    errors.append(str(exc))
                except Exception:  # pragma: no cover - unexpected failure logged for debugging
                    current_app.logger.exception(
                        "Failed to update access token signing configuration"
                    )
                    errors.append(
                        _(u"Failed to update the access token signing configuration.")
                    )
        elif action == "update-app-config-fields":
            app_selected = set(request.form.getlist("app_config_selected"))
            app_overrides = {
                key: request.form.get(f"app_config_new[{key}]")
                for key, definition in application_definitions.items()
                if definition.editable and f"app_config_new[{key}]" in request.form
            }
            app_use_defaults = {
                key
                for key, definition in application_definitions.items()
                if definition.editable
                and request.form.get(f"app_config_use_default[{key}]") == "1"
            }
            if not app_selected:
                errors.append(
                    _(
                        u"To save changes, select at least one setting and check its \"Update\" box."
                    )
                )
            else:
                updates: Dict[str, Any] = {}
                remove_keys: list[str] = []
                previous_config = dict(context["application_config"])
                for key in app_selected:
                    definition = application_definitions.get(key)
                    if definition is None:
                        errors.append(_(u"Unknown application setting: %(key)s", key=key))
                        continue
                    if not definition.editable:
                        label = definition.label or key
                        errors.append(
                            _(u"%(setting)s is read-only and cannot be modified.", setting=label)
                        )
                        continue
                    if key in app_use_defaults:
                        remove_keys.append(key)
                        continue
                    raw_value = request.form.get(f"app_config_new[{key}]")
                    try:
                        parsed_value = _parse_setting_value(key, definition, raw_value)
                    except ValueError as exc:
                        errors.append(str(exc))
                        continue
                    updates[key] = parsed_value
                if not errors:
                    SystemSettingService.update_application_settings(
                        updates, remove_keys=remove_keys
                    )
                    from webapp import _apply_persisted_settings

                    _apply_persisted_settings(current_app)
                    relogin_previous_config = previous_config
                    success_message = _(u"Application configuration updated.")
        elif action == "update-cors":
            cors_overrides = {
                key: request.form.get(f"cors_new[{key}]")
                for key, definition in cors_definitions.items()
                if definition.editable and f"cors_new[{key}]" in request.form
            }
            cors_use_defaults = {
                key
                for key, definition in cors_definitions.items()
                if definition.editable
                and request.form.get(f"cors_use_default[{key}]") == "1"
            }

            definition = cors_definitions.get("allowedOrigins")
            if definition is None:
                errors.append(_(u"Unknown CORS setting: %(key)s", key="allowedOrigins"))
            else:
                updates: Dict[str, Any] = {}
                remove_keys: list[str] = []
                if "allowedOrigins" in cors_use_defaults:
                    remove_keys.append("allowedOrigins")
                else:
                    raw_value = request.form.get("cors_new[allowedOrigins]")
                    try:
                        parsed_value = _parse_setting_value("allowedOrigins", definition, raw_value)
                    except ValueError as exc:
                        errors.append(str(exc))
                    else:
                        invalid_origins = [
                            origin
                            for origin in parsed_value
                            if origin != "*" and "://" not in origin
                        ]
                        if invalid_origins:
                            errors.append(
                                _(u"Each origin must be a full URL (e.g., https://example.com) or '*'. Invalid values: %(origins)s",
                                  origins=", ".join(invalid_origins))
                            )
                        else:
                            updates["allowedOrigins"] = parsed_value
                if not errors:
                    SystemSettingService.update_cors_settings(
                        updates, remove_keys=remove_keys
                    )
                    from webapp import _apply_persisted_settings

                    _apply_persisted_settings(current_app)
                    success_message = _(u"CORS allowed origins updated.")
        else:
            errors.append(_(u"Unknown action."))

        if success_message and not errors:
            context = _build_config_context()
            if action == "update-app-config-fields" and relogin_previous_config is not None:
                warnings.extend(
                    _detect_relogin_changes(
                        relogin_previous_config,
                        context["application_config"],
                        context["application_definitions"],
                    )
                )
            if is_ajax:
                payload = _serialize_config_context(context)
                payload.update(
                    {
                        "status": "success",
                        "message": success_message,
                        "action": action,
                    }
                )
                if warnings:
                    payload["warnings"] = warnings
                return jsonify(payload)

            for message in warnings:
                flash(message, "warning")
            flash(success_message, "success")
            return redirect(url_for("admin.show_config"))

        if errors:
            if is_ajax:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": errors[0],
                            "errors": errors,
                            "action": action,
                        }
                    ),
                    400,
                )

            for message in errors:
                flash(message, "danger")
            for message in warnings:
                flash(message, "warning")
            context = _build_config_context(
                app_overrides=app_overrides,
                app_selected=app_selected,
                app_use_defaults=app_use_defaults,
                cors_overrides=cors_overrides,
                cors_use_defaults=cors_use_defaults,
                builtin_signing_secret=builtin_secret_override,
            )

    if request.method == "GET" and is_ajax:
        payload = _serialize_config_context(context)
        payload.update({"status": "success", "action": "fetch"})
        return jsonify(payload)

    return render_template(
        "admin/config_view.html",
        signing_setting=context["signing_setting"],
        server_signing_groups=context["server_signing_groups"],
        builtin_signing_secret=context["builtin_signing_secret"],
        application_sections=context["application_sections"],
        application_fields=context["application_fields"],
        cors_fields=context["cors_fields"],
        application_config_updated_at=context["application_config_updated_at"],
        application_config_description=context["application_config_description"],
        cors_config_updated_at=context["cors_config_updated_at"],
        cors_config_description=context["cors_config_description"],
        signing_config_updated_at=context["signing_config_updated_at"],
    )

# バージョン情報表示ページ（管理者のみ）
@bp.route("/version")
@login_required
def show_version():
    if not current_user.can("system:manage"):
        return _(u"You do not have permission to access this page."), 403
    from core.version import get_version_info
    version_info = get_version_info()
    try:
        flask_version = importlib_metadata.version("flask")
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover - environment dependent
        flask_version = getattr(flask, "__version__", None)

    try:
        werkzeug_version = importlib_metadata.version("werkzeug")
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover - environment dependent
        werkzeug_version = None

    system_info = {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "flask_version": flask_version,
        "werkzeug_version": werkzeug_version,
        "environment": getattr(current_app, "env", None),
        "debug": current_app.debug,
        "hostname": socket.gethostname(),
    }
    return render_template(
        "admin/version_view.html",
        version_info=version_info,
        system_info=system_info,
    )


@bp.route("/data-files")
@login_required
def show_data_files():
    if not current_user.can("system:manage"):
        return _(u"You do not have permission to access this page."), 403

    directory_definitions = [
        ("MEDIA_ORIGINALS_DIRECTORY", _("Original Media Directory")),
        ("MEDIA_THUMBNAILS_DIRECTORY", _("Thumbnail Directory")),
        ("MEDIA_PLAYBACK_DIRECTORY", _("Playback Directory")),
        ("MEDIA_LOCAL_IMPORT_DIRECTORY", _("Local Import Directory")),
    ]
    directory_keys = [config_key for config_key, _ in directory_definitions]
    selected_key = request.args.get("directory") or directory_keys[0]
    if selected_key not in directory_keys:
        selected_key = directory_keys[0]

    default_per_page = 50
    per_page = request.args.get("per_page", type=int) or default_per_page
    if per_page <= 0:
        per_page = default_per_page
    per_page = min(per_page, 500)

    per_page_options = [25, 50, 100, 200]
    if per_page not in per_page_options:
        per_page_select_options = sorted({*per_page_options, per_page})
    else:
        per_page_select_options = per_page_options

    filter_query = request.args.get("q", "").strip()
    page = request.args.get("page", type=int) or 1
    if page <= 0:
        page = 1

    directories: list[dict] = []
    selected_directory: dict | None = None
    service = settings.storage.service()

    for config_key, label in directory_definitions:
        area = service.for_key(config_key)
        candidates = area.candidates()
        base_path = area.first_existing()
        effective_base = base_path or (candidates[0] if candidates else None)
        exists = bool(effective_base and service.exists(effective_base))

        summary = {
            "config_key": config_key,
            "label": label,
            "base_path": effective_base,
            "candidates": candidates,
            "exists": exists,
            "is_selected": config_key == selected_key,
        }
        directories.append(summary)

        if not summary["is_selected"]:
            continue

        selected_directory = dict(summary)
        selected_directory.update(
            {
                "files": [],
                "total_files": 0,
                "total_size_bytes": 0,
                "total_size_display": _format_bytes(0),
                "matching_size_bytes": 0,
                "matching_size_display": _format_bytes(0),
                "filter_active": bool(filter_query),
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_pages": 1,
                    "total_matching": 0,
                    "start_index": 0,
                    "end_index": 0,
                    "has_prev": False,
                    "has_next": False,
                    "prev_url": None,
                    "next_url": None,
                    "first_url": None,
                    "last_url": None,
                    "pages": [],
                },
            }
        )

        if not (effective_base and exists):
            continue

        total_files = 0
        total_size = 0
        matching_count = 0
        matching_size = 0
        page_files: list[dict] = []
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        lower_query = filter_query.lower()

        for rel_path, size in _iter_directory_entries(service, effective_base):
            total_files += 1
            total_size += size

            if lower_query and lower_query not in rel_path.lower():
                continue

            if start_index <= matching_count < end_index:
                page_files.append(
                    {
                        "name": rel_path,
                        "size_bytes": size,
                        "size_display": _format_bytes(size),
                    }
                )

            matching_count += 1
            matching_size += size

        if matching_count:
            total_pages = (matching_count + per_page - 1) // per_page
        else:
            total_pages = 1

        final_page = page
        if matching_count and page > total_pages:
            final_page = total_pages
            start_index = (final_page - 1) * per_page
            end_index = start_index + per_page
            page_files = []
            current_index = 0
            for rel_path, size in _iter_directory_entries(service, effective_base):
                if lower_query and lower_query not in rel_path.lower():
                    continue
                if start_index <= current_index < end_index:
                    page_files.append(
                        {
                            "name": rel_path,
                            "size_bytes": size,
                            "size_display": _format_bytes(size),
                        }
                    )
                current_index += 1

        if not matching_count:
            final_page = 1
            start_index = 0
            end_index = 0
        else:
            end_index = min(start_index + per_page, matching_count)

        base_query = {
            "directory": selected_key,
            "per_page": per_page,
        }
        if filter_query:
            base_query["q"] = filter_query

        pagination_pages = _build_pagination_pages(final_page, total_pages)
        pagination_page_links = [
            {
                "number": number,
                "url": url_for("admin.show_data_files", **base_query, page=number),
            }
            for number in pagination_pages
        ]

        pagination = {
            "page": final_page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_matching": matching_count,
            "start_index": start_index,
            "end_index": end_index,
            "has_prev": final_page > 1,
            "has_next": final_page < total_pages,
            "prev_url": url_for("admin.show_data_files", **base_query, page=final_page - 1)
            if final_page > 1
            else None,
            "next_url": url_for("admin.show_data_files", **base_query, page=final_page + 1)
            if final_page < total_pages
            else None,
            "first_url": url_for("admin.show_data_files", **base_query, page=1)
            if final_page > 1
            else None,
            "last_url": url_for("admin.show_data_files", **base_query, page=total_pages)
            if final_page < total_pages
            else None,
            "pages": pagination_page_links,
        }

        selected_directory.update(
            {
                "files": page_files,
                "total_files": total_files,
                "total_size_bytes": total_size,
                "total_size_display": _format_bytes(total_size),
                "matching_size_bytes": matching_size,
                "matching_size_display": _format_bytes(matching_size),
                "pagination": pagination,
            }
        )

    return render_template(
        "admin/data_files.html",
        directories=directories,
        selected_directory=selected_directory,
        filter_query=filter_query,
        per_page=per_page,
        per_page_options=per_page_select_options,
    )

# TOTPリセット
@bp.route("/user/<int:user_id>/reset-totp", methods=["POST"])
@login_required
def user_reset_totp(user_id):
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    user = User.query.get_or_404(user_id)
    # TOTPシークレットをリセット（Noneにする）
    user.totp_secret = None
    db.session.commit()
    flash(_("TOTP secret reset for user."), "success")
    return redirect(url_for("admin.user"))

# ユーザー削除
@bp.route("/user/<int:user_id>/delete", methods=["POST"])
@login_required
def user_delete(user_id):
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash(_("You cannot delete yourself."), "error")
        return redirect(url_for("admin.user"))
    db.session.delete(user)
    db.session.commit()
    flash(_("User deleted successfully."), "success")
    return redirect(url_for("admin.user"))

# ユーザーロール変更
@bp.route("/user/<int:user_id>/role", methods=["POST"])
@login_required
def user_change_role(user_id):
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    user = User.query.get_or_404(user_id)
    role_ids = request.form.getlist("roles")
    if not role_ids:
        flash(_("At least one role must be selected."), "error")
        return redirect(url_for("admin.user"))

    try:
        unique_role_ids = {int(role_id) for role_id in role_ids if role_id}
    except ValueError:
        flash(_("Invalid role selection."), "error")
        return redirect(url_for("admin.user"))

    if not unique_role_ids:
        flash(_("At least one role must be selected."), "error")
        return redirect(url_for("admin.user"))

    selected_roles = Role.query.filter(Role.id.in_(unique_role_ids)).all()
    if len(selected_roles) != len(unique_role_ids):
        flash(_("Selected role does not exist."), "error")
        return redirect(url_for("admin.user"))

    user.roles = selected_roles

    if user.id == current_user.id:
        active_role_id = session.get("active_role_id")
        selected_ids = {role.id for role in selected_roles}
        if active_role_id not in selected_ids:
            if len(selected_ids) == 1:
                session["active_role_id"] = selected_roles[0].id
            else:
                session.pop("active_role_id", None)
    db.session.commit()
    flash(_("User roles updated."), "success")
    return redirect(url_for("admin.user"))

# ユーザーのロール編集画面
@bp.route("/user/<int:user_id>/edit-roles", methods=["GET"])
@login_required
def user_edit_roles(user_id):
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    user = User.query.get_or_404(user_id)
    roles = Role.query.all()
    return render_template("admin/user_role_edit.html", user=user, roles=roles)

# ユーザー追加
@bp.route("/user/add", methods=["GET", "POST"])
@login_required
def user_add():
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    roles = Role.query.all()
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        role_id = request.form.get("role")
        if not email or not password or not role_id:
            flash(_("Email, password, and role are required."), "error")
            return render_template("admin/user_add.html", roles=roles)
        if User.query.filter_by(email=email).first():
            flash(_("Email already exists."), "error")
            return render_template("admin/user_add.html", roles=roles)
        role_obj = Role.query.get(int(role_id))
        if not role_obj:
            flash(_("Selected role does not exist."), "error")
            return render_template("admin/user_add.html", roles=roles)
        u = User(email=email)
        u.set_password(password)
        u.roles.append(role_obj)
        db.session.add(u)
        db.session.commit()
        flash(_("User created successfully."), "success")
        return redirect(url_for("admin.user"))
    return render_template("admin/user_add.html", roles=roles)


@bp.route("/user", methods=["GET"])
@login_required
def user():
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    users = User.query.all()
    roles = Role.query.all()
    return render_template("admin/admin_users.html", users=users, roles=roles)


@bp.route("/permissions", methods=["GET"])
@login_required
def permissions():
    if not current_user.can('permission:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    search = request.args.get("search", "").strip()
    sort = request.args.get("sort", "id")
    order = request.args.get("order", "asc")

    query = Permission.query
    if search:
        query = query.filter(Permission.code.contains(search))

    if sort not in ["id", "code"]:
        sort = "id"
    sort_column = getattr(Permission, sort)
    if order == "desc":
        sort_column = sort_column.desc()
    else:
        sort_column = sort_column.asc()

    perms = query.order_by(sort_column).all()
    return render_template(
        "admin/permissions.html", permissions=perms, search=search, sort=sort, order=order
    )


@bp.route("/permissions/add", methods=["GET", "POST"])
@login_required
def permission_add():
    if not current_user.can('permission:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    if request.method == "POST":
        code = request.form.get("code")
        if not code:
            flash(_("Code is required."), "error")
            return render_template("admin/permission_edit.html", permission=None)
        if Permission.query.filter_by(code=code).first():
            flash(_("Permission already exists."), "error")
            return render_template("admin/permission_edit.html", permission=None)
        p = Permission(code=code)
        db.session.add(p)
        db.session.commit()
        flash(_("Permission created successfully."), "success")
        return redirect(url_for("admin.permissions"))
    return render_template("admin/permission_edit.html", permission=None)


@bp.route("/permissions/<int:perm_id>/edit", methods=["GET", "POST"])
@login_required
def permission_edit(perm_id):
    if not current_user.can('permission:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    perm = Permission.query.get_or_404(perm_id)
    if request.method == "POST":
        code = request.form.get("code")
        if not code:
            flash(_("Code is required."), "error")
            return render_template("admin/permission_edit.html", permission=perm)
        perm.code = code
        db.session.commit()
        flash(_("Permission updated."), "success")
        return redirect(url_for("admin.permissions"))
    return render_template("admin/permission_edit.html", permission=perm)


@bp.route("/permissions/<int:perm_id>/delete", methods=["POST"])
@login_required
def permission_delete(perm_id):
    if not current_user.can('permission:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    perm = Permission.query.get_or_404(perm_id)
    db.session.delete(perm)
    db.session.commit()
    flash(_("Permission deleted."), "success")
    return redirect(url_for("admin.permissions"))


@bp.route("/roles", methods=["GET"])
@login_required
def roles():
    if not current_user.can('role:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    roles = Role.query.all()
    return render_template("admin/roles.html", roles=roles)


@bp.route("/roles/add", methods=["GET", "POST"])
@login_required
def role_add():
    if not current_user.can('role:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    permissions = Permission.query.all()
    if request.method == "POST":
        name = request.form.get("name")
        perm_ids = request.form.getlist("permissions")
        if not name:
            flash(_("Name is required."), "error")
            return render_template("admin/role_edit.html", role=None, permissions=permissions, selected=[])
        if Role.query.filter_by(name=name).first():
            flash(_("Role already exists."), "error")
            return render_template("admin/role_edit.html", role=None, permissions=permissions, selected=[])
        role = Role(name=name)
        for pid in perm_ids:
            perm = Permission.query.get(int(pid))
            if perm:
                role.permissions.append(perm)
        db.session.add(role)
        db.session.commit()
        flash(_("Role created successfully."), "success")
        return redirect(url_for("admin.roles"))
    return render_template("admin/role_edit.html", role=None, permissions=permissions, selected=[])


@bp.route("/roles/<int:role_id>/edit", methods=["GET", "POST"])
@login_required
def role_edit(role_id):
    if not current_user.can('role:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    role = Role.query.get_or_404(role_id)
    permissions = Permission.query.all()
    if request.method == "POST":
        name = request.form.get("name")
        perm_ids = request.form.getlist("permissions")
        if not name:
            flash(_("Name is required."), "error")
            return render_template("admin/role_edit.html", role=role, permissions=permissions, selected=[p.id for p in role.permissions])
        role.name = name
        role.permissions = []
        for pid in perm_ids:
            perm = Permission.query.get(int(pid))
            if perm:
                role.permissions.append(perm)
        db.session.commit()
        flash(_("Role updated."), "success")
        return redirect(url_for("admin.roles"))
    selected = [p.id for p in role.permissions]
    return render_template("admin/role_edit.html", role=role, permissions=permissions, selected=selected)


@bp.route("/roles/<int:role_id>/delete", methods=["POST"])
@login_required
def role_delete(role_id):
    if not current_user.can('role:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    role = Role.query.get_or_404(role_id)
    db.session.delete(role)
    db.session.commit()
    flash(_("Role deleted."), "success")
    return redirect(url_for("admin.roles"))

# Google Accounts管理
@bp.route("/google-accounts", methods=["GET"])
@login_required
def google_accounts():
    from core.models.google_account import GoogleAccount

    # 管理者は全てのアカウントを表示、一般ユーザーは自分のアカウントのみ表示
    if current_user.can('user:manage'):
        accounts = GoogleAccount.query.all()
    else:
        accounts = GoogleAccount.query.filter_by(user_id=current_user.id).all()

    return render_template("admin/google_accounts.html", accounts=accounts)


def _extract_service_account_payload() -> dict:
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict()

    active_raw = data.get("active_flg", True)
    if isinstance(active_raw, str):
        active_value = active_raw.strip().lower() in {"1", "true", "on", "yes"}
    else:
        active_value = bool(active_raw)

    return {
        "name": data.get("name", ""),
        "description": data.get("description"),
        "certificate_group_code": data.get("certificate_group_code", ""),
        "scope_names": data.get("scope_names", ""),
        "active_flg": active_value,
    }


def _list_server_signing_certificate_groups() -> list[dict]:
    now = datetime.now(timezone.utc)
    results: list[dict] = []
    groups = [
        group
        for group in ListCertificateGroupsUseCase().execute()
        if group.usage_type == UsageType.SERVER_SIGNING
    ]

    for group in groups:
        certificates = ListIssuedCertificatesUseCase().execute(
            UsageType.SERVER_SIGNING,
            group_code=group.group_code,
        )

        latest_entry: dict | None = None
        for certificate in certificates:
            revoked_at = _to_utc(certificate.revoked_at)
            if revoked_at is not None and revoked_at <= now:
                continue
            expires_at = _to_utc(certificate.expires_at)
            if expires_at is not None and expires_at <= now:
                continue
            try:
                default_certificate_services.private_key_store.get(certificate.kid)
            except CertificatePrivateKeyNotFoundError:
                continue

            subject = ""
            if certificate.certificate is not None:
                try:
                    subject = certificate.certificate.subject.rfc4514_string()
                except Exception:  # pragma: no cover - unexpected parsing issues
                    subject = ""

            latest_entry = {
                "kid": certificate.kid,
                "issued_at": _to_utc(certificate.issued_at),
                "expires_at": expires_at,
                "algorithm": certificate.jwk.get("alg"),
                "subject": subject,
            }
            break

        results.append(
            {
                "group_code": group.group_code,
                "group_label": group.display_name or group.group_code,
                "latest_certificate": latest_entry,
            }
        )

    results.sort(key=lambda item: ((item["group_label"] or "").lower(), item["group_code"]))
    return results


def _to_utc(value):
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_bytes(num: int) -> str:
    """人間が読みやすい形式にバイト数を整形."""

    step = 1024.0
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(num)
    for unit in units:
        if value < step or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= step
    return f"{value:.1f} PB"


def _iter_directory_entries(service: StorageService, base_dir: str):
    """指定ディレクトリ内のファイルをソートして列挙."""

    for root, dirs, filenames in service.walk(base_dir):
        dirs.sort()
        filenames.sort()
        for filename in filenames:
            file_path = service.join(root, filename)
            try:
                size = service.size(file_path)
            except OSError:
                size = 0
            rel_path = os.path.relpath(file_path, base_dir)
            yield service.normalize_path(rel_path), size


def _build_pagination_pages(page: int, total_pages: int, window: int = 2) -> list[int]:
    """ページ番号の表示用リストを生成."""

    if total_pages <= 0:
        return [1]
    start = max(page - window, 1)
    end = min(page + window, total_pages)
    return list(range(start, end + 1))
