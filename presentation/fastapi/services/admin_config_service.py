"""Admin config service functions (FastAPI version - no Flask deps)."""
from __future__ import annotations

import logging
import os
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
    # Import route helpers from web (pure data functions - no Flask deps at call time)
    from presentation.web.admin.routes import (
        _normalise_allowed_origins,
        _collect_application_definitions,
        _prepare_application_field_models,
        _collect_cors_definitions,
        _build_cors_field_rows,
    )

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
    # Delegate to web version - it's a pure data function
    from presentation.web.admin.routes import _parse_setting_value as _web_parse
    return _web_parse(key, definition, raw_value)


__all__ = [
    "_HIDDEN_APPLICATION_SETTING_KEYS",
    "_RELOGIN_REQUIRED_KEYS",
    "_detect_relogin_changes",
    "_build_config_context",
    "_serialize_config_context",
    "_list_server_signing_certificate_groups",
    "_parse_setting_value",
]
