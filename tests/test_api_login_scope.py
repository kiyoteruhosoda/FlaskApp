import importlib
import os
import uuid

import importlib
import os
import uuid

import jwt
import pytest
from flask import g

from core.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_CORS_SETTINGS,
)

from webapp.services.token_service import TokenService


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
    Config = config_module.Config

    Config.SQLALCHEMY_ENGINE_OPTIONS = {}
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
    from core.models.user import Permission, Role, User

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
        verification = TokenService.verify_access_token(data["access_token"])
        assert verification is not None
        user, scope = verification
        assert user.id == scoped_user.id
        assert scope == {"read:cert", "write:cert"}

        with app.test_request_context():
            g.current_token_scope = scope
            assert user.can("read:cert")
            assert not user.can("read:user")


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
