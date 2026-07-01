"""管理APIのユーザー作成/更新でのメール形式バリデーションと、
不正な形式のメールを持つユーザーがログインを試みた際のエラーハンドリングを検証する。
"""
from __future__ import annotations

import uuid

import pytest

from shared.kernel.database.db import db
from shared.infrastructure.models.user import Permission, Role, User


def _create_admin(app_context, *perm_codes: str) -> User:
    perms = []
    for code in perm_codes:
        p = Permission(code=code)
        db.session.add(p)
        perms.append(p)

    role = Role(name=f"admin-{uuid.uuid4().hex[:6]}")
    role.permissions = perms
    db.session.add(role)

    user = User(email=f"admin-{uuid.uuid4().hex[:8]}@example.com")
    user.set_password("pass")
    user.roles.append(role)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, user: User):
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


@pytest.fixture
def client(app_context):
    return app_context.test_client()


@pytest.mark.usefixtures("app_context")
class TestAdminUserEmailValidation:
    def test_create_user_rejects_invalid_email(self, client, app_context):
        admin = _create_admin(app_context, "user:manage")
        _login(client, admin)

        res = client.post(
            "/api/admin/users",
            json={"email": "not-an-email", "password": "password123"},
        )
        assert res.status_code == 400
        assert res.get_json()["error"] == "invalid_email"

    def test_update_user_rejects_invalid_email(self, client, app_context):
        admin = _create_admin(app_context, "user:manage")
        _login(client, admin)

        create_res = client.post(
            "/api/admin/users",
            json={"email": "valid@example.com", "password": "password123"},
        )
        user_id = create_res.get_json()["user"]["id"]

        res = client.put(f"/api/admin/users/{user_id}", json={"email": "still-not-an-email"})
        assert res.status_code == 400
        assert res.get_json()["error"] == "invalid_email"

    def test_login_with_malformed_stored_email_returns_json_error_not_500(self, client, app_context):
        """既存の不正な形式emailユーザーがログインを試みても、
        エラーハンドラがクラッシュせず 422 と JSON メッセージを返すこと。"""
        user = User(email="legacy-bad-email")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

        res = client.post(
            "/api/auth/login",
            json={"email": "legacy-bad-email", "password": "password123"},
        )
        assert res.status_code == 422
        data = res.get_json()
        assert data["error"] == "validation_failed"
        assert "email" in data["details"]["json"]
