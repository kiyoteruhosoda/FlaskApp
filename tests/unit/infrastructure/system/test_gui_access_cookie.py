import uuid

import pytest


@pytest.fixture()
def app(app_context):
    app = app_context
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def _create_gui_user(app):
    from webapp.extensions import db
    from core.models.user import Permission, Role, User

    with app.app_context():
        gui_perm = Permission(code="gui:view")
        dashboard_perm = Permission(code="dashboard:view")
        role = Role(name=f"gui-{uuid.uuid4().hex[:8]}")
        role.permissions.extend([gui_perm, dashboard_perm])
        user = User(email=f"cookie-{uuid.uuid4().hex[:8]}@example.com")
        user.set_password("pass")
        user.roles.append(role)
        db.session.add_all([gui_perm, dashboard_perm, role, user])
        db.session.commit()
        return user.email


def _extract_access_cookie(response):
    for header in response.headers.getlist("Set-Cookie"):
        if header.startswith("access_token="):
            return header
    return ""


def test_access_cookie_not_secure_for_local_http_when_secure_enforced(app, client):
    app.config["SESSION_COOKIE_SECURE"] = True
    email = _create_gui_user(app)

    response = client.post(
        "/api/login",
        json={"email": email, "password": "pass", "scope": "gui:view dashboard:view"},
        base_url="http://localhost",
    )

    assert response.status_code == 200
    cookie_header = _extract_access_cookie(response)
    assert cookie_header
    assert "Secure" not in cookie_header


def test_access_cookie_remains_secure_on_https_when_enforced(app, client):
    app.config["SESSION_COOKIE_SECURE"] = True
    email = _create_gui_user(app)

    response = client.post(
        "/api/login",
        json={"email": email, "password": "pass", "scope": "gui:view"},
        base_url="https://example.com",
    )

    assert response.status_code == 200
    cookie_header = _extract_access_cookie(response)
    assert cookie_header
    assert "Secure" in cookie_header


def test_access_cookie_secure_on_https_even_without_flag(app, client):
    app.config["SESSION_COOKIE_SECURE"] = False
    email = _create_gui_user(app)

    response = client.post(
        "/api/login",
        json={"email": email, "password": "pass", "scope": "gui:view"},
        base_url="https://example.com",
    )

    assert response.status_code == 200
    cookie_header = _extract_access_cookie(response)
    assert cookie_header
    assert "Secure" in cookie_header
