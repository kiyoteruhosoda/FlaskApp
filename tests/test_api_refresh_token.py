import os
import pytest
import uuid


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("data")
    db_path = tmp_path / "test.db"
    os.environ["SECRET_KEY"] = "test"
    os.environ["JWT_SECRET_KEY"] = "jwt-secret"
    os.environ["DATABASE_URI"] = f"sqlite:///{db_path}"
    from webapp.config import BaseApplicationSettings
    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app
    app = create_app()
    app.config.update(TESTING=True)
    from webapp.extensions import db
    from core.models.user import User
    with app.app_context():
        db.create_all()
        # ユニークなメールアドレスを使用
        unique_email = f"u{uuid.uuid4().hex[:8]}@example.com"
        u = User(email=unique_email)
        u.set_password("pass")
        db.session.add(u)
        db.session.commit()
        # テスト用にユーザー情報を保存
        app.test_user_email = unique_email
    yield app


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


def login(client, app, *, token: str | None = None):
    payload = {"email": app.test_user_email, "password": "pass"}
    if token:
        payload["token"] = token
    res = client.post("/api/login", json=payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["requires_role_selection"] is False
    assert data["scope"] == ""
    assert data["token_type"] == "Bearer"
    return data["access_token"], data["refresh_token"]


def test_login_returns_refresh_token(client, app):
    access, refresh = login(client, app)
    assert access
    assert refresh


def test_refresh_works(client, app):
    old_access, refresh = login(client, app)
    res = client.post("/api/refresh", json={"refresh_token": refresh})
    assert res.status_code == 200
    data = res.get_json()
    assert data["access_token"] != old_access
    assert data["refresh_token"] != refresh
    assert data["scope"] == ""
    assert data["token_type"] == "Bearer"


def test_refresh_invalid_token(client, app):
    res = client.post("/api/refresh", json={"refresh_token": "invalid"})
    assert res.status_code == 401


def test_refresh_inactive_user(client, app):
    _, refresh = login(client, app)

    from webapp.extensions import db
    from core.models.user import User

    with app.app_context():
        user = User.query.filter_by(email=app.test_user_email).first()
        assert user is not None
        user.is_active = False
        db.session.commit()

    res = client.post("/api/refresh", json={"refresh_token": refresh})
    assert res.status_code == 401
