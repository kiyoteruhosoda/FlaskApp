from __future__ import annotations

import os
from typing import Any, Dict


def test_remember_cookie_secure_inherits_session(monkeypatch):
    # 環境変数を設定
    monkeypatch.setenv("DATABASE_URI", "sqlite:///:memory:")
    
    from webapp.services import system_setting_service

    def _load_application_config_payload(cls) -> Dict[str, Any]:
        return {"SESSION_COOKIE_SECURE": True}

    def _load_cors_config(cls) -> Dict[str, Any]:
        return {"allowedOrigins": []}

    monkeypatch.setattr(
        system_setting_service.SystemSettingService,
        "load_application_config_payload",
        classmethod(_load_application_config_payload),
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
    # 環境変数を設定
    monkeypatch.setenv("DATABASE_URI", "sqlite:///:memory:")
    
    from webapp.services import system_setting_service

    def _load_cors_config(cls) -> Dict[str, Any]:
        return {"allowedOrigins": []}

    monkeypatch.setattr(
        system_setting_service.SystemSettingService,
        "load_cors_config",
        classmethod(_load_cors_config),
    )

    def _load_application_config_payload_false(cls) -> Dict[str, Any]:
        return {"SESSION_COOKIE_SECURE": False}

    monkeypatch.setattr(
        system_setting_service.SystemSettingService,
        "load_application_config_payload",
        classmethod(_load_application_config_payload_false),
    )

    from webapp import _apply_persisted_settings, create_app

    app = create_app()

    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["REMEMBER_COOKIE_SECURE"] is False

    def _load_application_config_payload_true(cls) -> Dict[str, Any]:
        return {"SESSION_COOKIE_SECURE": True}

    monkeypatch.setattr(
        system_setting_service.SystemSettingService,
        "load_application_config_payload",
        classmethod(_load_application_config_payload_true),
    )

    _apply_persisted_settings(app)

    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["REMEMBER_COOKIE_SECURE"] is True
