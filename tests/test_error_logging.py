import base64
import os
import importlib
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

    yield app

    del sys.modules["webapp.config"]
    del sys.modules["webapp"]


@pytest.fixture
def client(app):
    return app.test_client()


def test_error_logged(client):
    from core.models.error_log import ErrorLog

    resp = client.get("/boom")
    assert resp.status_code == 500
    with client.application.app_context():
        logs = ErrorLog.query.all()
        assert len(logs) == 1
        log = logs[0]
        assert log.message == "boom"
        assert log.path == "/boom"
