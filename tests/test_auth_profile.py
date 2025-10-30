import re
import uuid
from datetime import datetime, timezone

import pytest
from flask import url_for

from core.models.service_account import ServiceAccount
from core.models.user import Permission, Role, User
from webapp.extensions import db
from webapp.services.token_service import TokenService


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def _login(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def _create_user(email="user@example.com", password="password123"):
    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def _assign_permissions(user: User, *codes: str) -> list[str]:
    role = Role(name=f"role-{uuid.uuid4().hex[:8]}")
    db.session.add(role)

    assigned_codes: list[str] = []
    for code in codes:
        permission = Permission(code=code)
        db.session.add(permission)
        role.permissions.append(permission)
        assigned_codes.append(code)

    user.roles.append(role)
    db.session.add(user)
    db.session.commit()
    return assigned_codes


def _create_service_account(app, scopes=None):
    if scopes is None:
        scopes = set()

    with app.app_context():
        account = ServiceAccount(name=f"svc-{uuid.uuid4().hex[:8]}")
        account.set_scopes(scopes)
        db.session.add(account)
        db.session.commit()
        return account.service_account_id


def _service_account_login(client, account_id, scope=None):
    with client.application.app_context():
        account = ServiceAccount.query.get(account_id)
        token = TokenService.generate_service_account_access_token(
            account, scope=scope or set()
        )

    response = client.get(
        "/auth/servicelogin",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    return response


def test_profile_requires_login(client):
    app = client.application
    original_testing = app.config.get("TESTING")
    original_login_disabled = app.config.get("LOGIN_DISABLED")

    try:
        app.config["TESTING"] = False
        app.testing = False
        app.config["LOGIN_DISABLED"] = False
        response = client.get("/auth/profile")
    finally:
        if original_testing is not None:
            app.config["TESTING"] = original_testing
            app.testing = original_testing
        if original_login_disabled is not None:
            app.config["LOGIN_DISABLED"] = original_login_disabled
        else:
            app.config.pop("LOGIN_DISABLED", None)

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_profile_get_shows_preferences(client):
    user = _create_user()
    _login(client, user)

    response = client.get("/auth/profile")
    assert response.status_code == 200

    html = response.data.decode("utf-8")
    assert '<option value="ja" selected' in html
    assert '<option value="Asia/Tokyo" selected' in html

    # Localized current time should be displayed
    assert re.search(r"Local time \(Asia/Tokyo\).*<strong>", html, re.DOTALL)
    assert "UTC" in html
    assert "No active permissions." in html


def test_profile_shows_active_permissions_for_user(client):
    user = _create_user()
    codes = _assign_permissions(
        user,
        f"media:view:{uuid.uuid4().hex[:6]}",
        f"album:edit:{uuid.uuid4().hex[:6]}",
    )
    _login(client, user)

    response = client.get("/auth/profile")
    assert response.status_code == 200

    html = response.data.decode("utf-8")
    assert "Active permissions" in html
    for code in codes:
        assert code in html


def test_profile_post_updates_cookies_and_preferences(client):
    user = _create_user()
    _login(client, user)

    response = client.post(
        "/auth/profile",
        data={"language": "en", "timezone": "America/New_York"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    cookies = response.headers.getlist("Set-Cookie")
    assert any("lang=en" in cookie for cookie in cookies)
    assert any("tz=America/New_York" in cookie for cookie in cookies)

    # Follow redirect to ensure selections stick
    follow = client.get(response.headers["Location"])
    assert follow.status_code == 200
    html = follow.data.decode("utf-8")
    assert '<option value="en" selected' in html
    assert '<option value="America/New_York" selected' in html
    assert "Profile preferences updated." in html


def test_service_account_profile_hides_totp_button(client):
    account_id = _create_service_account(client.application)
    _service_account_login(client, account_id)

    response = client.get("/auth/profile")
    assert response.status_code == 200

    html = response.data.decode("utf-8")
    assert "/auth/setup_totp" not in html


def test_service_account_profile_shows_scoped_permissions(client):
    requested_scope = {"album:view"}
    account_id = _create_service_account(
        client.application,
        scopes=requested_scope | {"media:view"},
    )
    _service_account_login(client, account_id, scope=requested_scope)

    response = client.get("/auth/profile")
    assert response.status_code == 200

    html = response.data.decode("utf-8")
    assert "Active permissions" in html
    assert "album:view" in html
    assert "media:view" not in html


def test_service_account_cannot_access_totp_setup(client):
    account_id = _create_service_account(client.application)
    _service_account_login(client, account_id)

    with client.application.test_request_context():
        dashboard_url = url_for("dashboard.dashboard")

    response = client.get("/auth/setup_totp", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(dashboard_url)

    with client.session_transaction() as sess:
        flashes = sess.get("_flashes", [])
        assert any(
            category == "warning"
            and message == "Two-factor authentication is not available for service accounts."
            for category, message in flashes
        )
        assert "setup_totp_secret" not in sess


def test_totp_setup_with_bearer_token_authenticated_user(client):
    user = _create_user()

    with client.application.app_context():
        token = TokenService.generate_access_token(user)

    response = client.get(
        "/auth/setup_totp",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    html = response.data.decode("utf-8")
    assert "Setup Two-Factor Authentication" in html


def test_localtime_filter_respects_timezone_cookie(app_context):
    app = app_context
    dt = datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc)

    with app.test_request_context("/", headers=[("Cookie", "tz=America/New_York")]):
        app.preprocess_request()
        localtime_filter = app.jinja_env.filters["localtime"]
        formatted = localtime_filter(dt, "%Y-%m-%d %H:%M")

    assert formatted == "2024-01-01 10:00"
