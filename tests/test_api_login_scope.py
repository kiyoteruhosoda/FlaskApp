import importlib
import os
import uuid
from http.cookies import SimpleCookie

import jwt
import pytest
from flask import url_for

from core.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_CORS_SETTINGS,
)

from webapp.services.token_service import TokenService
from shared.application.authenticated_principal import AuthenticatedPrincipal
from core.models.user import Permission, Role, User
from core.models.service_account import ServiceAccount
from webapp.auth import SERVICE_LOGIN_SESSION_KEY


@pytest.fixture()
def app(tmp_path):
    tmp_dir = tmp_path / "login-scope"
    tmp_dir.mkdir()
    db_path = tmp_dir / "test.db"

    original_env = {}
    for key, value in {
        "SECRET_KEY": "test",
        "JWT_SECRET_KEY": "jwt-secret",
        "DATABASE_URI": f"sqlite:///{db_path}",
        "ACCESS_TOKEN_ISSUER": "test-issuer",
        "ACCESS_TOKEN_AUDIENCE": "test-audience",
    }.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    import webapp.config as config_module

    config_module = importlib.reload(config_module)
    BaseApplicationSettings = config_module.BaseApplicationSettings

    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app

    app = create_app()
    app.config.update(TESTING=True, LOGIN_DISABLED=False)

    funcs = app.before_request_funcs.get(None, [])
    app.before_request_funcs[None] = [
        func
        for func in funcs
        if getattr(func, "__name__", "") != "_apply_login_disabled_for_testing"
    ]

    from webapp.extensions import db
    from webapp.services.system_setting_service import SystemSettingService
    from webapp import _apply_persisted_settings

    with app.app_context():
        db.create_all()
        payload = {
            key: app.config.get(key, DEFAULT_APPLICATION_SETTINGS.get(key))
            for key in DEFAULT_APPLICATION_SETTINGS
        }
        payload.update(
            {
                "SECRET_KEY": os.environ["SECRET_KEY"],
                "JWT_SECRET_KEY": os.environ["JWT_SECRET_KEY"],
                "ACCESS_TOKEN_ISSUER": os.environ["ACCESS_TOKEN_ISSUER"],
                "ACCESS_TOKEN_AUDIENCE": os.environ["ACCESS_TOKEN_AUDIENCE"],
            }
        )
        SystemSettingService.upsert_application_config(payload)
        SystemSettingService.upsert_cors_config(
            app.config.get("CORS_ALLOWED_ORIGINS", DEFAULT_CORS_SETTINGS.get("allowedOrigins", []))
        )
        _apply_persisted_settings(app)

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


@pytest.fixture()
def scoped_user(app):
    from webapp.extensions import db

    with app.app_context():
        read_perm = Permission(code="read:cert")
        write_perm = Permission(code="write:cert")
        other_perm = Permission(code="read:user")
        db.session.add_all([read_perm, write_perm, other_perm])
        db.session.commit()

        role_reader = Role(name=f"reader-{uuid.uuid4().hex[:8]}")
        role_reader.permissions.append(read_perm)

        role_writer = Role(name=f"writer-{uuid.uuid4().hex[:8]}")
        role_writer.permissions.append(write_perm)

        role_other = Role(name=f"other-{uuid.uuid4().hex[:8]}")
        role_other.permissions.append(other_perm)

        user = User(email=f"scope-{uuid.uuid4().hex[:8]}@example.com")
        user.set_password("pass")
        user.roles.extend([role_reader, role_writer, role_other])

        db.session.add_all([role_reader, role_writer, role_other, user])
        db.session.commit()

        return user


@pytest.fixture()
def album_user(app):
    from webapp.extensions import db
    from core.models.user import Permission, Role, User

    with app.app_context():
        create_perm = Permission(code="album:create")
        edit_perm = Permission(code="album:edit")
        db.session.add_all([create_perm, edit_perm])
        db.session.flush()

        role = Role(name=f"album-{uuid.uuid4().hex[:8]}")
        role.permissions.extend([create_perm, edit_perm])

        user = User(email=f"album-{uuid.uuid4().hex[:8]}@example.com")
        user.set_password("pass")
        user.roles.append(role)

        db.session.add_all([role, user])
        db.session.commit()

        return user


@pytest.fixture()
def service_login_account(app):
    from webapp.extensions import db
    from core.models.service_account import ServiceAccount

    with app.app_context():
        account = ServiceAccount(name=f"svc-{uuid.uuid4().hex[:8]}")
        account.set_scopes({"totp:view"})
        db.session.add(account)
        db.session.commit()

        return {"account_id": account.service_account_id}



def _decode_scope(token: str) -> str:
    payload = jwt.decode(
        token,
        "jwt-secret",
        algorithms=["HS256"],
        audience=os.environ.get("ACCESS_TOKEN_AUDIENCE", "test-audience"),
        issuer=os.environ.get("ACCESS_TOKEN_ISSUER", "test-issuer"),
    )
    return payload.get("scope", "")


def test_login_applies_requested_scope_subset(app, client, scoped_user):
    payload = {
        "email": scoped_user.email,
        "password": "pass",
        "scope": "read:cert write:cert delete:cert",
    }

    response = client.post("/api/login", json=payload)
    assert response.status_code == 200
    data = response.get_json()

    assert data["scope"] == "read:cert write:cert"
    assert sorted(data["available_scopes"]) == ["read:cert", "read:user", "write:cert"]

    decoded_scope = _decode_scope(data["access_token"])
    assert decoded_scope == "read:cert write:cert"

    with app.app_context():
        principal = TokenService.verify_access_token(data["access_token"])
        assert isinstance(principal, AuthenticatedPrincipal)
        assert principal.id == scoped_user.id
        assert principal.scope == frozenset({"read:cert", "write:cert"})

        assert principal.can("read:cert")
        assert not principal.can("read:user")


def test_login_with_missing_scope_grants_no_permissions(client, scoped_user):
    payload = {"email": scoped_user.email, "password": "pass"}

    response = client.post("/api/login", json=payload)
    assert response.status_code == 200
    data = response.get_json()

    assert data["scope"] == ""
    assert _decode_scope(data["access_token"]) == ""


def test_login_rejects_scope_not_in_roles(client, scoped_user):
    payload = {
        "email": scoped_user.email,
        "password": "pass",
        "scope": "maintenance:edit write:cert",
    }

    response = client.post("/api/login", json=payload)
    assert response.status_code == 200
    data = response.get_json()

    # maintenance:edit は保有ロールに含まれないため除外される
    assert data["scope"] == "write:cert"
    assert _decode_scope(data["access_token"]) == "write:cert"


def _load_cookies(response) -> SimpleCookie:
    cookies = SimpleCookie()
    for header in response.headers.getlist("Set-Cookie"):
        cookies.load(header)
    return cookies


def _assert_cookie_cleared(response) -> None:
    headers = response.headers.getlist("Set-Cookie")
    assert not any(
        "access_token=" in header and "Max-Age=0" not in header for header in headers
    )
    cookies = _load_cookies(response)
    if "access_token" in cookies:
        assert cookies["access_token"].value == ""


def test_login_cookie_requires_gui_scope(app, client):
    from webapp.extensions import db

    with app.app_context():
        gui_perm = Permission(code="gui:view")
        manage_perm = Permission(code="user:manage")
        role = Role(name=f"gui-role-{uuid.uuid4().hex[:8]}")
        role.permissions.extend([gui_perm, manage_perm])

        user = User(email=f"gui-{uuid.uuid4().hex[:8]}@example.com")
        user.set_password("pass")
        user.roles.append(role)

        db.session.add_all([gui_perm, manage_perm, role, user])
        db.session.commit()

        user_email = user.email

    without_gui_response = client.post(
        "/api/login",
        json={
            "email": user_email,
            "password": "pass",
            "scope": ["user:manage"],
        },
    )
    assert without_gui_response.status_code == 200
    without_gui_data = without_gui_response.get_json()
    assert without_gui_data["scope"] == "user:manage"

    _assert_cookie_cleared(without_gui_response)

    with_gui_response = client.post(
        "/api/login",
        json={
            "email": user_email,
            "password": "pass",
            "scope": ["user:manage", "gui:view"],
        },
    )
    assert with_gui_response.status_code == 200
    with_gui_data = with_gui_response.get_json()
    assert with_gui_data["scope"] == "gui:view user:manage"

    with_gui_cookies = _load_cookies(with_gui_response)
    assert "access_token" in with_gui_cookies
    assert with_gui_cookies["access_token"].value != ""


def test_refresh_cookie_requires_gui_scope(app, client):
    from webapp.extensions import db

    with app.app_context():
        gui_perm = Permission(code="gui:view")
        manage_perm = Permission(code="user:manage")
        role = Role(name=f"refresh-role-{uuid.uuid4().hex[:8]}")
        role.permissions.extend([gui_perm, manage_perm])

        user = User(email=f"refresh-{uuid.uuid4().hex[:8]}@example.com")
        user.set_password("pass")
        user.roles.append(role)

        db.session.add_all([gui_perm, manage_perm, role, user])
        db.session.commit()

        user_email = user.email

    without_gui_login = client.post(
        "/api/login",
        json={
            "email": user_email,
            "password": "pass",
            "scope": ["user:manage"],
        },
    )
    assert without_gui_login.status_code == 200
    without_gui_tokens = without_gui_login.get_json()
    assert without_gui_tokens is not None
    _assert_cookie_cleared(without_gui_login)

    without_gui_refresh = client.post(
        "/api/refresh",
        json={"refresh_token": without_gui_tokens["refresh_token"]},
    )
    assert without_gui_refresh.status_code == 200
    _assert_cookie_cleared(without_gui_refresh)

    with_gui_login = client.post(
        "/api/login",
        json={
            "email": user_email,
            "password": "pass",
            "scope": ["user:manage", "gui:view"],
        },
    )
    assert with_gui_login.status_code == 200
    with_gui_tokens = with_gui_login.get_json()
    assert with_gui_tokens is not None
    with_gui_login_cookies = _load_cookies(with_gui_login)
    assert "access_token" in with_gui_login_cookies
    assert with_gui_login_cookies["access_token"].value != ""

    with_gui_refresh = client.post(
        "/api/refresh",
        json={"refresh_token": with_gui_tokens["refresh_token"]},
    )
    assert with_gui_refresh.status_code == 200
    with_gui_refresh_cookies = _load_cookies(with_gui_refresh)
    assert "access_token" in with_gui_refresh_cookies
    assert with_gui_refresh_cookies["access_token"].value != ""


def test_scoped_token_enforces_permissions(client, album_user):
    payload = {
        "email": album_user.email,
        "password": "pass",
        "scope": "album:create",
    }

    login_response = client.post("/api/login", json=payload)
    assert login_response.status_code == 200
    tokens = login_response.get_json()

    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    create_response = client.post(
        "/api/albums",
        json={"name": "Scoped Album"},
        headers=headers,
    )
    assert create_response.status_code == 201
    album_id = create_response.get_json()["album"]["id"]

    update_response = client.put(
        f"/api/albums/{album_id}",
        json={"name": "Updated"},
        headers=headers,
    )
    assert update_response.status_code == 403
    assert update_response.get_json()["error"] == "forbidden"


def test_service_login_sets_scope_and_redirects(app, client, service_login_account):
    with app.app_context():
        account = ServiceAccount.query.get(service_login_account["account_id"])
        token = TokenService.generate_service_account_access_token(account, scope={"totp:view"})

    with app.test_request_context():
        dashboard_path = url_for("dashboard.dashboard")

    response = client.get(
        "/auth/servicelogin",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith(dashboard_path)

    with client.session_transaction() as sess:
        assert sess.get("active_role_id") is None
        assert sess.get(SERVICE_LOGIN_SESSION_KEY) is True
        assert sess.get("_user_id") == f"system:{service_login_account['account_id']}"

    totp_response = client.get("/totp/")
    assert totp_response.status_code == 200

    cookie_headers = response.headers.getlist("Set-Cookie")
    assert any(header.startswith("access_token=") for header in cookie_headers)


def test_service_login_honors_next_parameter(app, client, service_login_account):
    with app.app_context():
        account = ServiceAccount.query.get(service_login_account["account_id"])
        token = TokenService.generate_service_account_access_token(account, scope={"totp:view"})

    response = client.get(
        "/auth/servicelogin",
        query_string={"next": "/totp/"},
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/totp/")


def test_service_login_does_not_require_role_selection(app, client, service_login_account):
    with app.app_context():
        account = ServiceAccount.query.get(service_login_account["account_id"])
        token = TokenService.generate_service_account_access_token(account, scope={"totp:view"})

    response = client.get(
        "/auth/servicelogin",
        query_string={"next": "/totp/"},
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/totp/")

    with client.session_transaction() as sess:
        assert sess.get("role_selection_next") is None
        assert sess.get(SERVICE_LOGIN_SESSION_KEY) is True
        assert sess.get("active_role_id") is None

    totp_response = client.get("/totp/")
    assert totp_response.status_code == 200


def test_service_login_denies_scope_when_token_missing(app, client, service_login_account):
    with app.app_context():
        account = ServiceAccount.query.get(service_login_account["account_id"])
        token = TokenService.generate_service_account_access_token(account, scope={"totp:view"})

    response = client.get(
        "/auth/servicelogin",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )

    assert response.status_code == 302

    # remove the access token cookie to simulate external deletion
    client.delete_cookie("access_token")

    restricted_response = client.get("/totp/")
    assert restricted_response.status_code in {302, 401, 403}


def test_service_login_rejects_invalid_token(client):
    response = client.get(
        "/auth/servicelogin",
        headers={"Authorization": "Bearer invalid-token"},
        follow_redirects=False,
    )

    assert response.status_code == 401


def test_service_login_requires_token_for_anonymous(client):
    response = client.get("/auth/servicelogin")

    assert response.status_code == 400




def test_service_login_rejects_individual_token(app, client):
    with app.app_context():
        from webapp.extensions import db

        perm = Permission.query.filter_by(code="totp:view").one_or_none()
        if perm is None:
            perm = Permission(code="totp:view")
            db.session.add(perm)
            db.session.flush()

        role = Role(name=f"totp-user-{uuid.uuid4().hex[:8]}")
        role.permissions.append(perm)

        user = User(email=f"person-{uuid.uuid4().hex[:8]}@example.com")
        user.set_password("pass")
        user.roles.append(role)

        db.session.add_all([role, user])
        db.session.commit()

        token = TokenService.generate_access_token(user, scope={"totp:view"})

    response = client.get(
        "/auth/servicelogin",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )

    assert response.status_code == 401


def test_service_login_rejects_query_token(app, client, service_login_account):
    with app.app_context():
        account = ServiceAccount.query.get(service_login_account["account_id"])
        token = TokenService.generate_service_account_access_token(account, scope={"totp:view"})

    response = client.get(
        "/auth/servicelogin",
        query_string={"token": token},
        follow_redirects=False,
    )

    assert response.status_code == 400


def test_service_login_mismatch_invalidates_session(app, client, service_login_account):
    with app.app_context():
        account = ServiceAccount.query.get(service_login_account["account_id"])
        token = TokenService.generate_service_account_access_token(account, scope={"totp:view"})

    login_response = client.get(
        "/auth/servicelogin",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=False,
    )

    assert login_response.status_code == 302

    with client.session_transaction() as sess:
        assert sess.get(SERVICE_LOGIN_SESSION_KEY) is True
        assert sess.get("_user_id") is not None

    with app.app_context():
        from webapp.extensions import db

        other_account = ServiceAccount(name=f"svc-mismatch-{uuid.uuid4().hex[:6]}")
        other_account.set_scopes({"totp:view"})
        db.session.add(other_account)
        db.session.commit()

        mismatch_token = TokenService.generate_service_account_access_token(
            other_account, scope={"totp:view"}
        )

    client.set_cookie("access_token", mismatch_token, domain="localhost")

    mismatch_response = client.get("/totp/", follow_redirects=False)

    assert mismatch_response.status_code in {302, 401, 403}

    cookie_headers = mismatch_response.headers.getlist("Set-Cookie")
    assert any("access_token=" in header and "Max-Age=0" in header for header in cookie_headers)

    with client.session_transaction() as sess:
        assert sess.get(SERVICE_LOGIN_SESSION_KEY) is None
        assert sess.get("_user_id") is None
