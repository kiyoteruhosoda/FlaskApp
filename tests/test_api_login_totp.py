import importlib
import os
import uuid

import pyotp
import pytest


@pytest.fixture()
def app(tmp_path):
    tmp_dir = tmp_path / "login-totp"
    tmp_dir.mkdir()
    db_path = tmp_dir / "test.db"

    original_env = {}
    for key, value in {
        "SECRET_KEY": "test",
        "JWT_SECRET_KEY": "jwt-secret",
        "DATABASE_URI": f"sqlite:///{db_path}",
    }.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    import webapp.config as config_module

    config_module = importlib.reload(config_module)
    BaseApplicationSettings = config_module.BaseApplicationSettings

    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app

    app = create_app()
    app.config.update(TESTING=True)

    from webapp.extensions import db

    with app.app_context():
        db.create_all()

    yield app

    with app.app_context():
        db.session.remove()
        db.drop_all()

    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture()
def client(app):
    return app.test_client()


def test_api_login_requires_totp(client, app):
    from webapp.extensions import db
    from core.models.user import User

    with app.app_context():
        secret = pyotp.random_base32()
        totp_user = User(email=f"totp-{uuid.uuid4().hex[:8]}@example.com", totp_secret=secret)
        totp_user.set_password("pass")
        db.session.add(totp_user)
        db.session.commit()
        totp_email = totp_user.email

    res = client.post("/api/login", json={"email": totp_email, "password": "pass"})
    assert res.status_code == 401
    assert res.get_json()["error"] == "totp_required"

    res = client.post(
        "/api/login",
        json={"email": totp_email, "password": "pass", "token": "000000"},
    )
    assert res.status_code == 401
    assert res.get_json()["error"] == "invalid_totp"

    valid_token = pyotp.TOTP(secret).now()
    res = client.post(
        "/api/login",
        json={"email": totp_email, "password": "pass", "token": valid_token},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["requires_role_selection"] is False
    assert data["redirect_url"].endswith("/dashboard/")


def test_api_login_accepts_string_scope(client, app):
    from webapp.extensions import db
    from core.models.user import Permission, Role, User

    with app.app_context():
        gui_permission = Permission(code="gui:view")
        dashboard_permission = Permission(code="dashboard:view")
        role = Role(name="string-scope-role")
        role.permissions.extend([gui_permission, dashboard_permission])
        user = User(email="scope-string@example.com")
        user.set_password("pass")
        user.roles.append(role)
        db.session.add_all([gui_permission, dashboard_permission, role, user])
        db.session.commit()
        email = user.email

    response = client.post(
        "/api/login",
        json={
            "email": email,
            "password": "pass",
            "scope": "dashboard:view gui:view",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert "gui:view" in payload["scope"].split()
    assert "dashboard:view" in payload["scope"].split()
    cookies = response.headers.getlist("Set-Cookie")
    assert any("access_token=" in cookie for cookie in cookies)
