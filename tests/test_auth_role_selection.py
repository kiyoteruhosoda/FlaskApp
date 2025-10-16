import os
import uuid

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

    from webapp.config import Config

    Config.SQLALCHEMY_ENGINE_OPTIONS = {}

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


def _create_user_with_roles(app, email, password, role_names):
    from webapp.extensions import db
    from core.models.user import User, Role

    with app.app_context():
        roles = []
        for name in role_names:
            role = Role(name=name)
            db.session.add(role)
            roles.append(role)
        user = User(email=email)
        user.set_password(password)
        user.roles = roles
        db.session.add(user)
        db.session.commit()
        role_ids = [role.id for role in roles]
        role_labels = [role.name for role in roles]
        return user.email, role_ids, role_labels


def test_login_redirects_to_role_selection(client, app):
    email, role_ids, role_names = _create_user_with_roles(
        app, "multi@example.com", "pass", ["admin", "editor"]
    )

    response = client.post(
        "/auth/login",
        data={"email": email, "password": "pass"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/select-role")

    selection_page = client.get("/auth/select-role")
    assert selection_page.status_code == 200
    for name in role_names:
        assert name.encode() in selection_page.data


def test_role_selection_sets_active_role(client, app):
    email, role_ids, role_names = _create_user_with_roles(
        app, "choose@example.com", "pass", ["admin", "editor"]
    )

    client.post("/auth/login", data={"email": email, "password": "pass"})

    response = client.post(
        "/auth/select-role",
        data={"active_role": str(role_ids[0])},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard/")

    with client.session_transaction() as sess:
        assert sess["active_role_id"] == role_ids[0]

    # Invalid selections should not clear the active role
    response = client.post(
        "/auth/select-role",
        data={"active_role": "all"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert b"Invalid role selection" in response.data

    with client.session_transaction() as sess:
        assert sess["active_role_id"] == role_ids[0]


def test_api_login_requires_role_selection(client, app):
    unique_email = f"api-multi-{uuid.uuid4().hex[:8]}@example.com"
    email, _, _ = _create_user_with_roles(
        app, unique_email, "pass", ["admin", "editor"]
    )

    res = client.post(
        "/api/login",
        json={"email": email, "password": "pass", "next": "/dashboard/library"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["requires_role_selection"] is True
    assert data["redirect_url"].endswith("/auth/select-role")
    assert "access_token" in data and "refresh_token" in data

    with client.session_transaction() as sess:
        assert sess.get("role_selection_next") == "/dashboard/library"
        assert "active_role_id" not in sess
