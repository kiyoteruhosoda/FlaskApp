from urllib.parse import urlparse

import pytest

from presentation.web.services.token_service import TokenService
from shared.infrastructure.models.user import User, Role, Permission
from shared.infrastructure.models.group import Group
from shared.kernel.database.db import db


def _login(client, user):
    from flask import session as flask_session
    from flask_login import login_user

    active_role_id = user.roles[0].id if user.roles else None

    with client.application.test_request_context():
        principal = TokenService.create_principal_for_user(user, active_role_id=active_role_id)
        login_user(principal)
        flask_session["_fresh"] = True
        persisted = dict(flask_session)

    with client.session_transaction() as session:
        session.update(persisted)
        session.modified = True


def _create_group_manager():
    # グループ管理は React SPA (GroupsPage) と同じく user:manage 権限で判定する
    # （"group:manage" は master_data.py の PERMISSION_CODES に存在せず、
    # どのロールにも付与できない無効な権限コードだった）。
    permission = Permission(code="user:manage")
    role = Role(name="group-admin")
    role.permissions.append(permission)

    user = User(email="manager@example.com")
    user.set_password("secret")
    user.roles.append(role)

    db.session.add_all([permission, role, user])
    db.session.commit()
    return user


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def test_group_page_requires_permission(client):
    user = User(email="user@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    _login(client, user)

    response = client.get("/admin/groups")
    assert response.status_code == 302
    with client.application.test_request_context():
        target = urlparse(response.headers["Location"])
        assert target.path == "/"


def test_group_page_serves_spa_shell_for_authorized_user(client):
    """権限がある場合、/admin/groups への直接アクセスが自己リダイレクトの
    無限ループにならず、SPA シェルを返すこと（302 にならないこと）。"""
    user = _create_group_manager()
    _login(client, user)

    response = client.get("/admin/groups")
    assert response.status_code == 200


def test_group_creation_and_child_assignment(client):
    user = _create_group_manager()
    _login(client, user)

    response = client.post(
        "/admin/groups/add",
        data={
            "name": "Engineering",
            "description": "Platform team",
            "parent_id": "",
            "user_ids": [str(user.id)],
        },
    )
    assert response.status_code == 302
    with client.application.app_context():
        parent = Group.query.filter_by(name="Engineering").one()
        assert parent.description == "Platform team"
        assert {member.id for member in parent.users} == {user.id}
        assert parent.parent is None

    child_response = client.post(
        "/admin/groups/add",
        data={
            "name": "QA",
            "description": "",
            "parent_id": str(parent.id),
            "user_ids": [],
        },
    )
    assert child_response.status_code == 302
    with client.application.app_context():
        child = Group.query.filter_by(name="QA").one()
        assert child.parent_id == parent.id


def test_group_edit_rejects_circular_hierarchy(client):
    """循環した親子関係を持つグループ更新が拒否されること。

    グループ編集 UI は React SPA が描画するため、SPA が利用する管理 API
    ``PUT /api/admin/groups/<id>`` で検証する。
    """
    # _create_group_manager() が付与する user:manage がそのままグループ更新 API
    # の権限要件を満たす。
    user = _create_group_manager()
    _login(client, user)

    parent = Group(name="Parent")
    child = Group(name="Child")
    child.assign_parent(parent)
    db.session.add_all([parent, child])
    db.session.commit()
    parent_id, child_id = parent.id, child.id

    response = client.put(
        f"/api/admin/groups/{parent_id}",
        json={"parentId": child_id},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "hierarchy_error"

    with client.application.app_context():
        refreshed = db.session.get(Group, parent_id)
        assert refreshed is not None
        assert refreshed.parent_id is None
