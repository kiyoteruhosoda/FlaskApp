import os
from datetime import datetime, timezone

import pytest


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    os.environ["SECRET_KEY"] = "test"
    os.environ["DATABASE_URI"] = f"sqlite:///{db_path}"
    thumbs = tmp_path / "thumbs"
    play = tmp_path / "play"
    thumbs.mkdir()
    play.mkdir()
    os.environ["FPV_NAS_THUMBS_DIR"] = str(thumbs)
    os.environ["FPV_NAS_PLAY_DIR"] = str(play)

    import importlib, sys
    import webapp.config as config_module
    importlib.reload(config_module)
    import webapp as webapp_module
    importlib.reload(webapp_module)
    from webapp.config import Config

    Config.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app

    app = create_app()
    app.config.update(TESTING=True)
    app.config["LAST_BEAT_AT"] = datetime.now(timezone.utc)

    from webapp.extensions import db
    with app.app_context():
        db.create_all()

    yield app
    del sys.modules["webapp.config"]
    del sys.modules["webapp"]


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
    assert "T" in resp.json["serverTime"] and "Z" in resp.json["serverTime"]

