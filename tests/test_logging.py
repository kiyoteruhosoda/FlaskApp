import base64
import os
import importlib
import json
import sys

import pytest


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    thumbs = tmp_path / "thumbs"
    play = tmp_path / "play"
    thumbs.mkdir()
    play.mkdir()
    os.environ["SECRET_KEY"] = "test"
    os.environ["DATABASE_URI"] = f"sqlite:///{db_path}"
    os.environ["GOOGLE_CLIENT_ID"] = ""
    os.environ["GOOGLE_CLIENT_SECRET"] = ""
    os.environ["OAUTH_TOKEN_KEY"] = base64.urlsafe_b64encode(b"0" * 32).decode()
    os.environ["FPV_DL_SIGN_KEY"] = base64.urlsafe_b64encode(b"1" * 32).decode()
    os.environ["FPV_URL_TTL_THUMB"] = "600"
    os.environ["FPV_URL_TTL_PLAYBACK"] = "600"
    os.environ["FPV_NAS_THUMBS_DIR"] = str(thumbs)
    os.environ["FPV_NAS_PLAY_DIR"] = str(play)

    import webapp.config as config_module
    importlib.reload(config_module)
    import webapp as webapp_module
    importlib.reload(webapp_module)
    from webapp import create_app
    from webapp.config import Config
    Config.SQLALCHEMY_ENGINE_OPTIONS = {}

    app = create_app()
    app.config.update(TESTING=True)

    from webapp.extensions import db

    with app.app_context():
        db.create_all()

        @app.route("/boom")
        def boom():
            raise Exception("boom")

        @app.route("/bad")
        def bad():
            return "bad", 502

        @app.post("/api/ping")
        def api_ping():
            return {"ok": True}

    yield app

    del sys.modules["webapp.config"]
    del sys.modules["webapp"]


@pytest.fixture
def client(app):
    return app.test_client()


def test_log_written(client):
    from core.models.log import Log

    resp = client.get("/boom")
    assert resp.status_code == 500
    with client.application.app_context():
        logs = Log.query.all()
        assert len(logs) == 1
        log = logs[0]
        data = json.loads(log.message)
        assert data["message"] == "boom"
        assert log.path.endswith("/boom")


def test_502_logged(client):
    from core.models.log import Log

    resp = client.get("/bad")
    assert resp.status_code == 502
    with client.application.app_context():
        logs = Log.query.all()
        assert len(logs) == 1
        log = logs[0]
        data = json.loads(log.message)
        assert data["status"] == 502
        assert log.path.endswith("/bad")


def test_api_request_response_logged(client):
    from core.models.log import Log

    resp = client.post("/api/ping", json={"hello": "world"})
    assert resp.status_code == 200
    with client.application.app_context():
        logs = Log.query.order_by(Log.id).all()
        assert len(logs) == 2
        req_log, resp_log = logs
        req_data = json.loads(req_log.message)
        resp_data = json.loads(resp_log.message)
        assert req_log.event == "api.input"
        assert resp_log.event == "api.output"
        assert req_data["method"] == "POST"
        assert req_data["json"] == {"hello": "world"}
        assert resp_data["status"] == 200
        assert resp_data["json"] == {"ok": True}
        assert req_log.request_id == resp_log.request_id
        assert req_log.path.endswith("/api/ping")
        assert resp_log.path.endswith("/api/ping")
