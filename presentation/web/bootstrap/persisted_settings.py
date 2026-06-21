"""DB 等に永続化された設定値を ``app.config`` へ反映する処理.

``create_app()`` から切り出した起動時設定ロードを担う。アプリケーション設定・
CORS 設定・メール設定を取得し、既定値とレガシーキーを考慮して ``app.config`` を
組み立てる。管理画面での設定更新後にも再適用される（公開関数
``apply_persisted_settings``）。
"""

from __future__ import annotations

from collections.abc import MutableMapping

from flask import Flask

from core.settings import settings
from core.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_CORS_SETTINGS,
)

from presentation.web.services.system_setting_service import SystemSettingService


def apply_persisted_settings(app: Flask) -> None:
    """Load persisted configuration values into ``app.config``."""

    try:
        stored_payload = SystemSettingService.load_application_config_payload()
    except Exception as exc:  # pragma: no cover - defensive fallback
        app.logger.warning("Failed to load application settings from DB: %s", exc)
        stored_payload = {}

    config_payload = dict(DEFAULT_APPLICATION_SETTINGS)
    config_payload.update(stored_payload)

    if stored_payload:
        for canonical_key, legacy_keys in settings._LEGACY_KEYS.items():
            if canonical_key in stored_payload:
                continue
            for legacy_key in legacy_keys:
                if legacy_key in stored_payload:
                    config_payload[canonical_key] = stored_payload[legacy_key]
                    break
    for key, value in config_payload.items():
        if key == "DATABASE_URI":
            continue
        if isinstance(value, dict):
            app.config[key] = dict(value)
        elif isinstance(value, list):
            app.config[key] = list(value)
        else:
            app.config[key] = value

    if "REMEMBER_COOKIE_SECURE" not in config_payload:
        app.config["REMEMBER_COOKIE_SECURE"] = bool(
            app.config.get("SESSION_COOKIE_SECURE", False)
        )

    try:
        cors_payload = SystemSettingService.load_cors_config()
    except Exception as exc:  # pragma: no cover - defensive fallback
        app.logger.warning("Failed to load CORS settings from DB: %s", exc)
        cors_payload = dict(DEFAULT_CORS_SETTINGS)
    allowed = cors_payload.get("allowedOrigins", [])
    if isinstance(allowed, str):
        allowed_origins = [segment.strip() for segment in allowed.split(",") if segment.strip()]
    elif isinstance(allowed, (list, tuple, set)):
        allowed_origins = [str(origin).strip() for origin in allowed if str(origin).strip()]
    else:
        allowed_origins = []
    app.config["CORS_ALLOWED_ORIGINS"] = tuple(allowed_origins)

    # メール設定を再適用
    from .extensions import mail

    mail_enabled = bool(config_payload.get("MAIL_ENABLED", False))

    if mail_enabled:
        app.config["MAIL_SERVER"] = config_payload.get("MAIL_SERVER", "")
        app.config["MAIL_PORT"] = config_payload.get("MAIL_PORT", 587)
        app.config["MAIL_USE_TLS"] = config_payload.get("MAIL_USE_TLS", True)
        app.config["MAIL_USE_SSL"] = config_payload.get("MAIL_USE_SSL", False)
        app.config["MAIL_USERNAME"] = config_payload.get("MAIL_USERNAME", "")
        app.config["MAIL_PASSWORD"] = config_payload.get("MAIL_PASSWORD", "")
        app.config["MAIL_DEFAULT_SENDER"] = config_payload.get("MAIL_DEFAULT_SENDER") or config_payload.get("MAIL_USERNAME", "")

        mail_state = mail.init_app(app)
        mail.state = mail_state
        mail.app = app
    else:
        extensions = getattr(app, "extensions", None)
        if isinstance(extensions, MutableMapping):
            extensions.pop("mailman", None)
        mail.state = None
        mail.app = None
