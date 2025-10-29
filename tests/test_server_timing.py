import base64
import importlib
import os
import sys

import pytest


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    thumbs = tmp_path / "thumbs"
    play = tmp_path / "play"
    thumbs.mkdir()
    play.mkdir()
    temp_env = {
        "SECRET_KEY": "test",
        "DATABASE_URI": f"sqlite:///{db_path}",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "ENCRYPTION_KEY": base64.urlsafe_b64encode(b"0" * 32).decode(),
        "MEDIA_DOWNLOAD_SIGNING_KEY": base64.urlsafe_b64encode(b"1" * 32).decode(),
        "MEDIA_THUMBNAIL_URL_TTL_SECONDS": "600",
        "MEDIA_PLAYBACK_URL_TTL_SECONDS": "600",
        "MEDIA_THUMBNAILS_DIRECTORY": str(thumbs),
        "MEDIA_PLAYBACK_DIRECTORY": str(play),
    }
    original_env = {key: os.environ.get(key) for key in temp_env}
    os.environ.update(temp_env)

    import webapp.config as config_module
    importlib.reload(config_module)
    import webapp as webapp_module
    importlib.reload(webapp_module)
    from webapp import create_app
    from webapp.config import BaseApplicationSettings
    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}

    app = create_app()
    app.config.update(TESTING=True)

    from webapp.extensions import db
    with app.app_context():
        db.create_all()

    try:
        yield app
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        del sys.modules["webapp.config"]
        del sys.modules["webapp"]


@pytest.fixture
def client(app):
    return app.test_client()


def test_server_timing_header(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Server-Timing" in resp.headers
    metric = resp.headers["Server-Timing"]
    assert metric.startswith("app;dur=")
    value = float(metric.split("dur=")[1])
    assert value >= 0

