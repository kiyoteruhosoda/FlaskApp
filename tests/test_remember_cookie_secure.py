from __future__ import annotations

from typing import Any, Dict


def test_remember_cookie_secure_inherits_session(monkeypatch):
    from webapp.services import system_setting_service

    def _load_application_config(cls) -> Dict[str, Any]:
        return {"SESSION_COOKIE_SECURE": True}

    def _load_cors_config(cls) -> Dict[str, Any]:
        return {"allowedOrigins": []}

    monkeypatch.setattr(
        system_setting_service.SystemSettingService,
        "load_application_config",
        classmethod(_load_application_config),
    )
    monkeypatch.setattr(
        system_setting_service.SystemSettingService,
        "load_cors_config",
        classmethod(_load_cors_config),
    )

    from webapp import create_app

    app = create_app()

    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["REMEMBER_COOKIE_SECURE"] is True


def test_remember_cookie_secure_updates_with_session_changes(monkeypatch):
    from webapp.services import system_setting_service

    def _load_cors_config(cls) -> Dict[str, Any]:
        return {"allowedOrigins": []}

    monkeypatch.setattr(
        system_setting_service.SystemSettingService,
        "load_cors_config",
        classmethod(_load_cors_config),
    )

    def _load_application_config_false(cls) -> Dict[str, Any]:
        return {"SESSION_COOKIE_SECURE": False}

    monkeypatch.setattr(
        system_setting_service.SystemSettingService,
        "load_application_config",
        classmethod(_load_application_config_false),
    )

    from webapp import _apply_persisted_settings, create_app

    app = create_app()

    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["REMEMBER_COOKIE_SECURE"] is False

    def _load_application_config_true(cls) -> Dict[str, Any]:
        return {"SESSION_COOKIE_SECURE": True}

    monkeypatch.setattr(
        system_setting_service.SystemSettingService,
        "load_application_config",
        classmethod(_load_application_config_true),
    )

    _apply_persisted_settings(app)

    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["REMEMBER_COOKIE_SECURE"] is True
