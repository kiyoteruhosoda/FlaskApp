"""Tests for CORS configuration derived from external files."""

from __future__ import annotations

import pytest

from webapp import create_app
from webapp.extensions import db
from webapp.services.system_setting_service import SystemSettingService
from core.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS
from webapp import _apply_persisted_settings


@pytest.fixture
def cors_client(monkeypatch):
    """Provide a Flask test client with CORS origins stored in the database."""

    allowed = [
        "https://frontend.example.com",
        "https://admin.example.com",
    ]

    monkeypatch.delenv("CORS_ALLOWED_ORIGINS_FILE", raising=False)
    monkeypatch.setenv("DATABASE_URI", "sqlite:///:memory:")

    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        payload = {
            key: app.config.get(key, DEFAULT_APPLICATION_SETTINGS.get(key))
            for key in DEFAULT_APPLICATION_SETTINGS
        }
        SystemSettingService.upsert_application_config(payload)
        SystemSettingService.upsert_cors_config(allowed)
        _apply_persisted_settings(app)

    with app.test_client() as client:
        yield client, allowed


def test_cors_headers_for_allowed_origin(cors_client):
    client, allowed = cors_client
    origin = allowed[0]

    response = client.get("/health/live", headers={"Origin": origin})

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert "Origin" in (response.headers.get("Vary") or "")
    assert client.application.config["CORS_ALLOWED_ORIGINS"] == tuple(allowed)


def test_cors_headers_absent_for_unlisted_origin(cors_client):
    client, _ = cors_client

    response = client.get(
        "/health/live",
        headers={"Origin": "https://untrusted.example.com"},
    )

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers
    assert "Access-Control-Allow-Credentials" not in response.headers


def test_cors_preflight_respects_configuration(cors_client):
    client, allowed = cors_client
    origin = allowed[-1]

    response = client.options(
        "/health/live",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, X-Custom",
        },
    )

    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert response.headers["Access-Control-Allow-Methods"] == "POST"
    assert response.headers["Access-Control-Allow-Headers"] == "Authorization, X-Custom"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert response.headers["Access-Control-Max-Age"] == "86400"
    assert "Origin" in (response.headers.get("Vary") or "")
