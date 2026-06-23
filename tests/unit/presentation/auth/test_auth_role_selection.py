import os
import uuid
from urllib.parse import parse_qs, urlparse

import pytest


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "role-select.db"

    original_env = {}
    for key, value in {
        "SECRET_KEY": "test",
        "JWT_SECRET_KEY": "jwt-test",
        "DATABASE_URI": f"sqlite:///{db_path}",
    }.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    from presentation.web.bootstrap.config import BaseApplicationSettings

    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}

    from presentation.web import create_app

    app = create_app()
    app.config.update(TESTING=True)

    from presentation.web.bootstrap.extensions import db

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


def _create_user_with_roles(app, email, password, role_names):
    from presentation.web.bootstrap.extensions import db
    from shared.infrastructure.models.user import User, Role, Permission

    with app.app_context():
        roles = []
        for name in role_names:
            role = Role(name=name)
            db.session.add(role)
            roles.append(role)
        dashboard_perm = (
            Permission.query.filter_by(code="dashboard:view").first()
            or Permission(code="dashboard:view")
        )
        if dashboard_perm.id is None:
            db.session.add(dashboard_perm)
        for role in roles:
            if dashboard_perm not in role.permissions:
                role.permissions.append(dashboard_perm)
        user = User(email=email)
        user.set_password(password)
        user.roles = roles
        db.session.add(user)
        db.session.commit()
        role_ids = [role.id for role in roles]
        role_labels = [role.name for role in roles]
        return user.email, role_ids, role_labels


def test_login_redirects_to_role_selection(client, app):
    """複数ロールのユーザーはログイン時にロール選択を要求されること。

    ロール選択画面は React SPA が描画するため、SPA が利用する
    ``POST /api/auth/login`` と ``GET /api/auth/roles`` で検証する。
    """
    email, role_ids, role_names = _create_user_with_roles(
        app, "multi@example.com", "pass", ["admin", "editor"]
    )

    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "pass"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["requires_role_selection"] is True
    assert urlparse(data["redirect_url"]).path == "/auth/select-role"

    # 利用可能なロール一覧が API から取得できること
    roles_response = client.get("/api/auth/roles")
    assert roles_response.status_code == 200
    roles_data = roles_response.get_json()
    returned_names = {role["name"] for role in roles_data["roles"]}
    for name in role_names:
        assert name in returned_names
    assert roles_data["requires_selection"] is True


def test_role_selection_preserves_next_parameter(client, app):
    email, role_ids, _ = _create_user_with_roles(
        app, "preserve-next@example.com", "pass", ["admin", "editor"]
    )

    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "pass", "next": "/certs/groups/create"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["requires_role_selection"] is True
    parsed = urlparse(data["redirect_url"])
    assert parsed.path == "/auth/select-role"
    assert parse_qs(parsed.query).get("next") == ["/certs/groups/create"]

    # ロール選択後は元の next 先へ遷移する redirect_url が返ること
    selection_response = client.post(
        "/api/auth/select-role",
        json={"role_id": role_ids[0]},
    )
    assert selection_response.status_code == 200
    assert selection_response.get_json()["redirect_url"] == "/certs/groups/create"


def test_role_selection_sets_active_role(client, app):
    email, role_ids, role_names = _create_user_with_roles(
        app, "choose@example.com", "pass", ["admin", "editor"]
    )

    login = client.post(
        "/api/auth/login", json={"email": email, "password": "pass"}
    )
    assert login.status_code == 200

    response = client.post(
        "/api/auth/select-role",
        json={"role_id": role_ids[0]},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["active_role"]["id"] == role_ids[0]
    assert data["redirect_url"].endswith("/dashboard/")

    with client.session_transaction() as sess:
        assert sess["active_role_id"] == role_ids[0]

    # 無効なロール選択はアクティブロールを変更しない
    response = client.post(
        "/api/auth/select-role",
        json={"role_id": 999999},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_role"

    with client.session_transaction() as sess:
        assert sess["active_role_id"] == role_ids[0]


def test_api_login_requires_role_selection(client, app):
    unique_email = f"api-multi-{uuid.uuid4().hex[:8]}@example.com"
    email, _, _ = _create_user_with_roles(
        app, unique_email, "pass", ["admin", "editor"]
    )

    res = client.post(
        "/api/auth/login",
        json={"email": email, "password": "pass", "next": "/dashboard/library"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["requires_role_selection"] is True
    redirect_url = data["redirect_url"]
    parsed_redirect = urlparse(redirect_url)
    assert parsed_redirect.path == "/auth/select-role"
    assert parse_qs(parsed_redirect.query).get("next") == ["/dashboard/library"]
    assert "access_token" in data and "refresh_token" in data
    assert data["token_type"] == "Bearer"

    with client.session_transaction() as sess:
        assert sess.get("role_selection_next") == "/dashboard/library"
        assert "active_role_id" not in sess
