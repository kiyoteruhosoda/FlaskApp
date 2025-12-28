from http.cookies import SimpleCookie

from flask import Flask, jsonify
import pytest

from webapp.api.blueprint import AuthEnforcedBlueprint
from webapp.api.health import skip_auth
from webapp.api.routes import API_LOGIN_SCOPE_SESSION_KEY, login_or_jwt_required
from webapp.auth.service_account_auth import require_service_account_scopes


def _register_routes(blueprint):
    app = Flask(__name__)
    app.register_blueprint(blueprint)


def test_route_registration_requires_auth_decorator():
    bp = AuthEnforcedBlueprint("test", __name__)

    with pytest.raises(RuntimeError):

        @bp.get("/forbidden")
        def forbidden_route():
            return "nope"


def test_route_registration_allows_skip_auth():
    bp = AuthEnforcedBlueprint("test", __name__)

    @bp.get("/health")
    @skip_auth
    def health_route():
        return "ok"

    _register_routes(bp)


def test_route_registration_allows_login_or_jwt_required():
    bp = AuthEnforcedBlueprint("test", __name__)

    @bp.get("/secure")
    @login_or_jwt_required
    def secure_route():
        return "ok"

    _register_routes(bp)


def test_route_registration_allows_service_account_auth():
    bp = AuthEnforcedBlueprint("test", __name__)

    @bp.get("/maintenance")
    @require_service_account_scopes(["maintenance:read"], audience=lambda _: "test")
    def maintenance_route():
        return "ok"

    _register_routes(bp)


def _get_cookie_value(client, name: str) -> str | None:
    cookies = getattr(client, "_cookies", {}) or {}
    for (domain, path, cookie_name), cookie in cookies.items():
        if cookie_name == name:
            return cookie.value
    return None


def test_login_or_jwt_required_regenerates_cookie_on_invalid_token(app_context):
    app = app_context

    with app.app_context():
        from core.models.user import Permission, Role, User
        from webapp.extensions import db

        manage_permission = Permission(code="user:manage")
        gui_permission = Permission(code="gui:view")
        admin_role = Role(name="admin-fallback")
        admin_role.permissions.extend([manage_permission, gui_permission])
        admin_user = User(email="fallback-admin@example.com")
        admin_user.set_password("pass")
        admin_user.roles.append(admin_role)
        db.session.add_all([manage_permission, admin_role, admin_user])
        db.session.commit()

        @app.route("/__test__/protected")
        @login_or_jwt_required
        def protected_route():
            return jsonify({"ok": True})

    client = app.test_client()
    login_response = client.post(
        "/api/login",
        json={
            "email": "fallback-admin@example.com",
            "password": "pass",
            "scope": ["user:manage", "gui:view"],
        },
    )
    assert login_response.status_code == 200
    login_payload = login_response.get_json()
    assert login_payload is not None
    refresh_token = login_payload["refresh_token"]

    refresh_response = client.post(
        "/api/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_response.status_code == 200
    refresh_cookies = SimpleCookie()
    for header in refresh_response.headers.getlist("Set-Cookie"):
        refresh_cookies.load(header)
    assert "access_token" in refresh_cookies
    original_cookie = refresh_cookies["access_token"].value

    with client.session_transaction() as session_state:
        assert set(session_state.get(API_LOGIN_SCOPE_SESSION_KEY, [])) == {"gui:view", "user:manage"}

    client.set_cookie("access_token", "malformed.token.value", domain="localhost", path="/")

    response = client.get("/__test__/protected")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    assert payload.get("ok") is True
    response_cookies = SimpleCookie()
    for header in response.headers.getlist("Set-Cookie"):
        response_cookies.load(header)
    assert "access_token" in response_cookies
    regenerated_cookie = response_cookies["access_token"].value
    assert regenerated_cookie != "malformed.token.value"
    assert regenerated_cookie != original_cookie

    access_cookie_headers = [
        header
        for header in response.headers.getlist("Set-Cookie")
        if header.startswith("access_token=")
    ]
    assert access_cookie_headers
    for header in access_cookie_headers:
        assert "HttpOnly" in header
        assert "Path=/" in header
        assert "SameSite=" in header

    client_cookie = _get_cookie_value(client, "access_token")
    assert client_cookie == regenerated_cookie

    with client.session_transaction() as session_state:
        assert set(session_state.get(API_LOGIN_SCOPE_SESSION_KEY, [])) == {"gui:view", "user:manage"}
