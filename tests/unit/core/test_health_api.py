import os
import os
from datetime import datetime, timezone

import pytest

from shared.kernel.settings.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_CORS_SETTINGS,
)


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    os.environ["SECRET_KEY"] = "test"
    os.environ["DATABASE_URI"] = f"sqlite:///{db_path}"
    thumbs = tmp_path / "thumbs"
    play = tmp_path / "play"
    thumbs.mkdir()
    play.mkdir()
    os.environ["MEDIA_THUMBNAILS_DIRECTORY"] = str(thumbs)
    os.environ["MEDIA_PLAYBACK_DIRECTORY"] = str(play)

    import importlib, sys
    import presentation.web.bootstrap.config as config_module
    import presentation.web as webapp_module
    from presentation.web.bootstrap.config import BaseApplicationSettings

    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from presentation.web import create_app

    app = create_app()
    app.config.update(TESTING=True)
    app.config["LAST_BEAT_AT"] = datetime.now(timezone.utc)

    from presentation.web.bootstrap.extensions import db
    from presentation.web.services.system_setting_service import SystemSettingService
    from presentation.web import _apply_persisted_settings

    with app.app_context():
        db.create_all()
        payload = {
            key: app.config.get(key, DEFAULT_APPLICATION_SETTINGS.get(key))
            for key in DEFAULT_APPLICATION_SETTINGS
        }
        payload.update(
            {
                "MEDIA_THUMBNAILS_DIRECTORY": str(thumbs),
                "MEDIA_PLAYBACK_DIRECTORY": str(play),
            }
        )
        SystemSettingService.upsert_application_config(payload)
        SystemSettingService.upsert_cors_config(
            app.config.get("CORS_ALLOWED_ORIGINS", DEFAULT_CORS_SETTINGS.get("allowedOrigins", []))
        )
        _apply_persisted_settings(app)

    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_health_live(client):
    resp = client.get("/api/health/live")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"


def test_health_ready(client):
    resp = client.get("/api/health/ready")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"


def test_health_beat(client, app):
    resp = client.get("/api/health/beat")
    assert resp.status_code == 200
    assert resp.json["lastBeatAt"] == app.config["LAST_BEAT_AT"].isoformat()
    assert "T" in resp.json["server_time"] and "Z" in resp.json["server_time"]


def test_healthz(client):
    resp = client.get("/api/healthz")
    assert resp.status_code == 200
    data = resp.json
    assert data["status"] == "ok"
    assert "version" in data
    assert "commit_hash" in data
    assert "branch" in data
    assert "build_date" in data
    assert "T" in data["server_time"] and data["server_time"].endswith("Z")

