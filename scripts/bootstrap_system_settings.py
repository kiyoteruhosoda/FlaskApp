#!/usr/bin/env python
"""Populate the system_settings table with application configuration."""
from __future__ import annotations

import json
import os
from typing import Any, Iterable

from webapp import create_app
from webapp.extensions import db
from webapp.services.system_setting_service import SystemSettingService
from core.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS

_BOOL_TRUE = {"1", "true", "yes", "on"}


def _coerce_value(key: str, value: str, template: Any) -> Any:
    if isinstance(template, bool):
        return value.strip().lower() in _BOOL_TRUE
    if isinstance(template, int) and not isinstance(template, bool):
        try:
            return int(value)
        except ValueError:
            return template
    if isinstance(template, float):
        try:
            return float(value)
        except ValueError:
            return template
    if isinstance(template, (list, tuple)):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        return [segment.strip() for segment in value.split(",") if segment.strip()]
    if template is None:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _load_application_settings_from_env() -> dict[str, Any]:
    values = dict(DEFAULT_APPLICATION_SETTINGS)
    for key, default in DEFAULT_APPLICATION_SETTINGS.items():
        raw = os.environ.get(key)
        if raw is None:
            continue
        values[key] = _coerce_value(key, raw, default)
    return values


def _load_cors_origins() -> Iterable[str]:
    raw = os.environ.get("CORS_ALLOWED_ORIGINS")
    if raw:
        return [segment.strip() for segment in raw.split(",") if segment.strip()]
    return []


def main() -> None:
    app = create_app()
    with app.app_context():
        payload = _load_application_settings_from_env()
        SystemSettingService.upsert_application_config(payload)
        cors_origins = list(_load_cors_origins())
        SystemSettingService.upsert_cors_config(cors_origins)
        db.session.commit()


if __name__ == "__main__":  # pragma: no cover
    main()
