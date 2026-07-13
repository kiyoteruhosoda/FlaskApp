"""Admin config service functions (FastAPI version - no Flask deps)."""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Dict

from shared.kernel.i18n.translation import gettext as _
from shared.infrastructure.models.system_setting import SystemSetting
from shared.kernel.settings.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_CORS_SETTINGS,
)
from bounded_contexts.certs.application.services import default_certificate_services
from bounded_contexts.certs.application.use_cases import (
    ListCertificateGroupsUseCase,
    ListIssuedCertificatesUseCase,
)
from bounded_contexts.certs.domain.exceptions import CertificatePrivateKeyNotFoundError
from bounded_contexts.certs.domain.usage import UsageType
from presentation.fastapi.admin.system_settings_definitions import (
    APPLICATION_SETTING_DEFINITIONS,
    APPLICATION_SETTING_SECTIONS,
    CORS_SETTING_DEFINITIONS,
    READONLY_APPLICATION_SETTING_KEYS,
    SettingFieldDefinition,
)
from presentation.fastapi.services.system_setting_service import (
    AccessTokenSigningSetting,
    AccessTokenSigningValidationError,
    SystemSettingService,
)

logger = logging.getLogger(__name__)

_HIDDEN_APPLICATION_SETTING_KEYS: frozenset[str] = frozenset({"JWT_SECRET_KEY"})
_RELOGIN_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "SECRET_KEY",
        "SESSION_COOKIE_SECURE",
        "SESSION_COOKIE_HTTPONLY",
        "SESSION_COOKIE_SAMESITE",
        "PERMANENT_SESSION_LIFETIME",
    }
)


def _to_utc(value):
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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

    # 空文字（空白のみ）の環境変数は「未設定」とみなす。Docker の env_file 等で
    # ``KEY=`` と空定義された環境変数を「環境変数で上書き済み（読み取り専用）」
    # として扱うと、管理画面で保存した DB 値が空欄表示で消えたように見えるため。
    env_value = os.environ.get(key)
    if env_value is not None and env_value.strip() == "":
        env_value = None
    if env_value is not None:
        value_source = "environment"
    elif stored_has_value:
        value_source = "database"
    else:
        value_source = "default"

    if key in override_values:
        form_value = override_values[key]
    elif stored_has_value:
        form_value = _value_to_form_string(definition, stored_value)
    else:
        form_value = _value_to_form_string(definition, current_value)

    current_json = _format_value_for_display(current_value)
    default_json = _format_value_for_display(default_value) if key in defaults else ""
    choices = definition.choice_labels()
    choices_text = " ".join(f"{value} {label}" for value, label in choices)

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
        "input_suffix": definition.input_suffix,
        "value_source": value_source,
        "env_value": env_value,
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
                except Exception:
                    subject = ""

            latest_entry = {
                "kid": certificate.kid,
                "subject": subject,
                "expires_at": _to_utc(certificate.expires_at).isoformat() if certificate.expires_at else None,
            }
            break

        results.append(
            {
                "group_code": group.group_code,
                "label": group.label or group.group_code,
                "latest_certificate": latest_entry,
            }
        )

    return results


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

    # Use os.environ instead of current_app.config for readonly keys
    readonly_application_values: dict[str, Any] = {}
    for key in READONLY_APPLICATION_SETTING_KEYS:
        if key in readonly_application_values:
            continue
        readonly_application_values[key] = os.environ.get(key)
    application_config = {**readonly_application_values, **application_config}

    cors_payload = SystemSettingService.load_cors_config_payload()
    cors_config = {**DEFAULT_CORS_SETTINGS, **cors_payload}
    effective_allowed_origins = _normalise_allowed_origins(())
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
    except AccessTokenSigningValidationError:
        signing_setting = AccessTokenSigningSetting(mode="server_signing")

    certificate_groups = _list_server_signing_certificate_groups()

    app_setting_record = SystemSetting.query.filter_by(setting_key="app.config").one_or_none()
    cors_setting_record = SystemSetting.query.filter_by(setting_key="app.cors").one_or_none()
    signing_record = SystemSetting.query.filter_by(setting_key="access_token_signing").one_or_none()

    builtin_secret_value = (
        builtin_signing_secret
        if builtin_signing_secret is not None
        else SystemSettingService.resolve_builtin_jwt_secret()
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

    return {
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


def _parse_setting_value(key: str, definition: SettingFieldDefinition, raw_value: str | None):
    label = definition.label or key
    if definition.data_type == "boolean":
        if raw_value not in {"true", "false"}:
            raise ValueError(_(u"Please choose a value for %(key)s.", key=label))
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


__all__ = [
    "_HIDDEN_APPLICATION_SETTING_KEYS",
    "_RELOGIN_REQUIRED_KEYS",
    "_normalise_allowed_origins",
    "_detect_relogin_changes",
    "_build_config_context",
    "_serialize_config_context",
    "_list_server_signing_certificate_groups",
    "_parse_setting_value",
]
