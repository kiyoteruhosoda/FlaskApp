"""Permission checks for the photo view UI."""

import uuid
from contextlib import contextmanager

import pytest

from flask import session as flask_session
from flask_login import login_user

from core.models.user import Permission, Role, User, db
from webapp.services.token_service import TokenService


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def _login(client, user: User) -> None:
    """Log the provided user into the test client session."""

    roles = list(getattr(user, "roles", []) or [])
    active_role_id = roles[0].id if roles else None
    with client.application.test_request_context():
        principal = TokenService.create_principal_for_user(
            user, active_role_id=active_role_id
        )
        login_user(principal)
        flask_session["_fresh"] = True
        persisted = dict(flask_session)

    with client.session_transaction() as session:
        session.update(persisted)
        session.modified = True


@contextmanager
def _require_auth_checks(client):
    """Temporarily enable permission enforcement during tests."""

    app = client.application
    original_testing = app.config.get("TESTING")
    original_login_disabled = app.config.get("LOGIN_DISABLED")
    app.config["TESTING"] = False
    app.config["LOGIN_DISABLED"] = False
    try:
        yield
    finally:
        if original_testing is None:
            app.config.pop("TESTING", None)
        else:
            app.config["TESTING"] = original_testing

        if original_login_disabled is None:
            app.config.pop("LOGIN_DISABLED", None)
        else:
            app.config["LOGIN_DISABLED"] = original_login_disabled


def _ensure_permission(code: str) -> Permission:
    permission = Permission.query.filter_by(code=code).one_or_none()
    if permission is None:
        permission = Permission(code=code)
        db.session.add(permission)
        db.session.flush()
    return permission


def _create_user_with_permissions(*perm_codes: str) -> User:
    permissions = [_ensure_permission(code) for code in perm_codes]
    role = Role(name=f"photo-view-role-{uuid.uuid4().hex[:8]}")
    role.permissions.extend(permissions)

    user = User(email=f"user-{uuid.uuid4().hex}@example.com")
    user.set_password("secret")
    user.roles.append(role)

    db.session.add_all([role, user])
    db.session.commit()

    return user


def test_settings_redirects_without_admin_permission(client):
    """Users lacking admin:photo-settings are redirected away from settings."""

    user = _create_user_with_permissions("media:view")
    _login(client, user)

    with _require_auth_checks(client):
        response = client.get("/photo-view/settings")

    # require_perms aborts with 403 which our HTML error handler maps to a
    # redirect back to the top page.
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_settings_page_available_with_admin_permission(client):
    """Users with the admin scope can open the settings screen."""

    user = _create_user_with_permissions("media:view", "admin:photo-settings")
    _login(client, user)

    with _require_auth_checks(client):
        response = client.get("/photo-view/settings")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Local Import Overview" in html


def test_session_home_hides_settings_button_without_admin_permission(client):
    """The photo view home page hides settings when admin scope is missing."""

    user = _create_user_with_permissions("media:view", "media:session")
    _login(client, user)

    with _require_auth_checks(client):
        response = client.get("/photo-view/session")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "/photo-view/settings" not in html


def test_session_home_shows_settings_button_with_admin_permission(client):
    """When the admin scope is granted the settings button becomes visible."""

    user = _create_user_with_permissions(
        "media:view", "media:session", "admin:photo-settings"
    )
    _login(client, user)

    with _require_auth_checks(client):
        response = client.get("/photo-view/session")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "/photo-view/settings" in html


def test_session_home_redirects_without_session_permission(client):
    """Users lacking media:session cannot open the session page."""

    user = _create_user_with_permissions("media:view")
    _login(client, user)

    with _require_auth_checks(client):
        response = client.get("/photo-view/session")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_media_page_available_without_session_permission(client):
    """The media listing remains accessible with only media:view."""

    user = _create_user_with_permissions("media:view")
    _login(client, user)

    with _require_auth_checks(client):
        response = client.get("/photo-view/media")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Media Gallery" in html


def test_root_redirects_to_albums(client):
    """Accessing /photo-view/ redirects to the albums view."""

    user = _create_user_with_permissions("media:view")
    _login(client, user)

    with _require_auth_checks(client):
        response = client.get("/photo-view/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/photo-view/albums")

