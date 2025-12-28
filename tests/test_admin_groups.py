from urllib.parse import urlparse

import pytest

from webapp.extensions import db
from webapp.services.token_service import TokenService
from core.models.user import User, Role, Permission
from core.models.group import Group


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
    permission = Permission(code="group:manage")
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
    user = _create_group_manager()
    _login(client, user)

    parent = Group(name="Parent")
    child = Group(name="Child")
    child.assign_parent(parent)
    db.session.add_all([parent, child])
    db.session.commit()

    response = client.post(
        f"/admin/groups/{parent.id}/edit",
        data={
            "name": "Parent",
            "description": "",
            "parent_id": str(child.id),
            "user_ids": [],
        },
    )
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "circular hierarchy" in html

    with client.application.app_context():
        refreshed = db.session.get(Group, parent.id)
        assert refreshed is not None
        assert refreshed.parent_id is None
