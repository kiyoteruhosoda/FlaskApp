import os
import importlib
import sys

import pytest


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    env = {
        "SECRET_KEY": "test",
        "DATABASE_URI": f"sqlite:///{db_path}",
        "JWT_SECRET_KEY": "dev-jwt-secret",
    }
    prev = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    import webapp.config as config_module
    importlib.reload(config_module)
    import webapp as webapp_module
    importlib.reload(webapp_module)
    from webapp.config import Config
    Config.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app
    app = create_app()
    app.config.update(TESTING=True)
    from webapp.extensions import db
    from core.models.user import User
    with app.app_context():
        db.create_all()
        u = User(email="u@example.com")
        u.set_password("pass")
        db.session.add(u)
        db.session.commit()
    yield app
    del sys.modules["webapp.config"]
    del sys.modules["webapp"]
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_refresh_flow(app):
    client = app.test_client()
    resp = client.post("/api/login", json={"email": "u@example.com", "password": "pass"})
    assert resp.status_code == 200
    access1 = resp.get_json()["access_token"]
    refresh1 = client.get_cookie("refresh_token").value

    resp2 = client.post("/api/refresh")
    assert resp2.status_code == 200
    access2 = resp2.get_json()["access_token"]
    refresh2 = client.get_cookie("refresh_token").value
    assert refresh1 != refresh2

    # old refresh token should be invalid
    client.set_cookie("refresh_token", refresh1)
    resp3 = client.post("/api/refresh")
    assert resp3.status_code == 401
