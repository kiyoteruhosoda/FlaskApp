from urllib.parse import urlparse

import pytest

from shared.infrastructure.models.user import User, Role, Permission
from shared.kernel.database.db import db


def _login(client, user):
    from flask import session as flask_session
    from flask_login import login_user
    from presentation.web.services.token_service import TokenService

    active_role_id = user.roles[0].id if user.roles else None

    with client.application.test_request_context():
        principal = TokenService.create_principal_for_user(user, active_role_id=active_role_id)
        login_user(principal)
        flask_session["_fresh"] = True
        persisted = dict(flask_session)

    with client.session_transaction() as session:
        session.update(persisted)
        session.modified = True


def _create_role_manager():
    # ロール一覧表示は React SPA (RolesPage) と同じく user:manage 権限で判定する。
    permission = Permission(code="user:manage")
    role = Role(name="role-admin")
    role.permissions.append(permission)

    user = User(email="role-manager@example.com")
    user.set_password("secret")
    user.roles.append(role)

    db.session.add_all([permission, role, user])
    db.session.commit()
    return user


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def test_roles_page_requires_permission(client):
    user = User(email="user@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    _login(client, user)

    response = client.get("/admin/roles")
    assert response.status_code == 302
    with client.application.test_request_context():
        target = urlparse(response.headers["Location"])
        assert target.path == "/"


def test_roles_page_serves_spa_shell_for_authorized_user(client):
    """権限がある場合、/admin/roles への直接アクセスが自己リダイレクトの
    無限ループにならず、SPA シェルを返すこと（302 にならないこと）。"""
    user = _create_role_manager()
    _login(client, user)

    response = client.get("/admin/roles")
    assert response.status_code == 200
