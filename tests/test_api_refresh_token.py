import os
import pytest


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("data")
    db_path = tmp_path / "test.db"
    os.environ["SECRET_KEY"] = "test"
    os.environ["JWT_SECRET_KEY"] = "jwt-secret"
    os.environ["DATABASE_URI"] = f"sqlite:///{db_path}"
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


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


def login(client):
    res = client.post("/api/login", json={"email": "u@example.com", "password": "pass"})
    assert res.status_code == 200
    data = res.get_json()
    return data["access_token"], data["refresh_token"]


def test_login_returns_refresh_token(client):
    access, refresh = login(client)
    assert access
    assert refresh


def test_refresh_works(client):
    old_access, refresh = login(client)
    res = client.post("/api/refresh", json={"refresh_token": refresh})
    assert res.status_code == 200
    data = res.get_json()
    assert data["access_token"] != old_access
    assert data["refresh_token"] != refresh


def test_refresh_invalid_token(client):
    res = client.post("/api/refresh", json={"refresh_token": "invalid"})
    assert res.status_code == 401

