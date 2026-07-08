"""T8: グループとロールの紐づけ — ユニットテスト。

グループへのロール付与と、グループ経由での権限波及をテストする。
"""
from __future__ import annotations

import uuid

import pytest

from shared.kernel.database.db import db
from shared.infrastructure.models.user import User, Role, Permission
from shared.infrastructure.models.group import Group


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _create_user_with_perm(*perm_codes: str) -> User:
    perms = [Permission(code=code) for code in perm_codes]
    role = Role(name=f"role-{uuid.uuid4().hex[:6]}")
    role.permissions = perms
    user = User(email=f"u-{uuid.uuid4().hex[:8]}@example.com")
    user.set_password("pass")
    user.roles.append(role)
    db.session.add_all([*perms, role, user])
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


# ---------------------------------------------------------------------------
# モデルレベル: グループへのロール付与と User.permissions 波及
# ---------------------------------------------------------------------------


class TestGroupRoleModel:
    """Group.roles と User.permissions の統合テスト（DB レベル）。"""

    def test_assign_role_to_group(self, app_context):
        """グループにロールを付与して取得できること。"""
        role = Role(name=f"grp-role-{uuid.uuid4().hex[:6]}")
        group = Group(name=f"grp-{uuid.uuid4().hex[:6]}")
        group.roles.append(role)
        db.session.add_all([role, group])
        db.session.commit()

        refreshed = db.session.get(Group, group.id)
        assert any(r.id == role.id for r in refreshed.roles)

    def test_user_inherits_permissions_from_group_role(self, app_context):
        """グループに付与されたロールの権限がユーザーへ波及すること。"""
        perm = Permission(code=f"media:view-{uuid.uuid4().hex[:6]}")
        role = Role(name=f"grp-role-{uuid.uuid4().hex[:6]}")
        role.permissions.append(perm)

        group = Group(name=f"grp-{uuid.uuid4().hex[:6]}")
        group.roles.append(role)

        user = User(email=f"u-{uuid.uuid4().hex[:8]}@example.com")
        user.set_password("pass")
        user.groups.append(group)

        db.session.add_all([perm, role, group, user])
        db.session.commit()

        refreshed = db.session.get(User, user.id)
        assert perm.code in refreshed.all_permissions

    def test_user_without_direct_role_gets_group_permission(self, app_context):
        """直接ロールを持たないユーザーでもグループ経由で権限を取得できること。"""
        perm = Permission(code=f"album:view-{uuid.uuid4().hex[:6]}")
        role = Role(name=f"grp-role-{uuid.uuid4().hex[:6]}")
        role.permissions.append(perm)

        group = Group(name=f"grp-{uuid.uuid4().hex[:6]}")
        group.roles.append(role)

        user = User(email=f"u-{uuid.uuid4().hex[:8]}@example.com")
        user.set_password("pass")
        user.groups.append(group)

        db.session.add_all([perm, role, group, user])
        db.session.commit()

        refreshed = db.session.get(User, user.id)
        # 直接のロールはなし
        assert len(refreshed.roles) == 0
        # グループ経由で権限が付与されている
        assert perm.code in refreshed.all_permissions

    def test_multiple_groups_roles_aggregated(self, app_context):
        """複数グループのロールが重複なく集約されること。"""
        perm_a = Permission(code=f"wiki:read-{uuid.uuid4().hex[:6]}")
        perm_b = Permission(code=f"wiki:write-{uuid.uuid4().hex[:6]}")
        role_a = Role(name=f"grp-role-a-{uuid.uuid4().hex[:6]}")
        role_b = Role(name=f"grp-role-b-{uuid.uuid4().hex[:6]}")
        role_a.permissions.append(perm_a)
        role_b.permissions.append(perm_b)

        group_a = Group(name=f"grp-a-{uuid.uuid4().hex[:6]}")
        group_a.roles.append(role_a)
        group_b = Group(name=f"grp-b-{uuid.uuid4().hex[:6]}")
        group_b.roles.append(role_b)

        user = User(email=f"u-{uuid.uuid4().hex[:8]}@example.com")
        user.set_password("pass")
        user.groups.extend([group_a, group_b])

        db.session.add_all([perm_a, perm_b, role_a, role_b, group_a, group_b, user])
        db.session.commit()

        refreshed = db.session.get(User, user.id)
        perms = refreshed.all_permissions
        assert perm_a.code in perms
        assert perm_b.code in perms

    def test_group_role_does_not_affect_other_users(self, app_context):
        """グループに所属しないユーザーには権限が波及しないこと。"""
        perm = Permission(code=f"secret:access-{uuid.uuid4().hex[:6]}")
        role = Role(name=f"grp-role-{uuid.uuid4().hex[:6]}")
        role.permissions.append(perm)

        group = Group(name=f"grp-{uuid.uuid4().hex[:6]}")
        group.roles.append(role)

        member = User(email=f"member-{uuid.uuid4().hex[:8]}@example.com")
        member.set_password("pass")
        member.groups.append(group)

        outsider = User(email=f"out-{uuid.uuid4().hex[:8]}@example.com")
        outsider.set_password("pass")

        db.session.add_all([perm, role, group, member, outsider])
        db.session.commit()

        refreshed_outsider = db.session.get(User, outsider.id)
        assert perm.code not in refreshed_outsider.all_permissions


# ---------------------------------------------------------------------------
# API レベル: GET/PUT /api/admin/groups/<id>/roles
# ---------------------------------------------------------------------------


class TestGroupRolesApi:
    """グループロール管理 API のテスト。"""

    def test_get_group_roles_requires_user_manage(self, client, app_context):
        """user:manage なしでは 403 が返ること。"""
        user = _create_user_with_perm()  # 権限なし
        _login(client, user)
        group = Group(name=f"grp-{uuid.uuid4().hex[:6]}")
        db.session.add(group)
        db.session.commit()

        res = client.get(f"/api/admin/groups/{group.id}/roles")
        assert res.status_code == 403

    def test_get_group_roles_not_found(self, client, app_context):
        """存在しないグループIDで 404 が返ること。"""
        user = _create_user_with_perm("user:manage")
        _login(client, user)

        res = client.get("/api/admin/groups/99999/roles")
        assert res.status_code == 404

    def test_get_group_roles_empty(self, client, app_context):
        """ロール未設定グループの場合、空リストが返ること。"""
        user = _create_user_with_perm("user:manage")
        _login(client, user)
        group = Group(name=f"grp-{uuid.uuid4().hex[:6]}")
        db.session.add(group)
        db.session.commit()

        res = client.get(f"/api/admin/groups/{group.id}/roles")
        assert res.status_code == 200
        data = res.get_json()
        assert data["groupId"] == group.id
        assert data["roles"] == []

    def test_put_group_roles_assigns_roles(self, client, app_context):
        """PUT でロールをグループに割り当てられること。"""
        user = _create_user_with_perm("user:manage")
        _login(client, user)
        role = Role(name=f"r-{uuid.uuid4().hex[:6]}")
        group = Group(name=f"grp-{uuid.uuid4().hex[:6]}")
        db.session.add_all([role, group])
        db.session.commit()

        res = client.put(
            f"/api/admin/groups/{group.id}/roles",
            json={"roleIds": [role.id]},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["updated"] is True
        assert any(r["id"] == role.id for r in data["roles"])

    def test_put_group_roles_clears_roles(self, client, app_context):
        """roleIds=[] で既存のロール割り当てをすべて解除できること。"""
        user = _create_user_with_perm("user:manage")
        _login(client, user)
        role = Role(name=f"r-{uuid.uuid4().hex[:6]}")
        group = Group(name=f"grp-{uuid.uuid4().hex[:6]}")
        group.roles.append(role)
        db.session.add_all([role, group])
        db.session.commit()

        res = client.put(
            f"/api/admin/groups/{group.id}/roles",
            json={"roleIds": []},
        )
        assert res.status_code == 200
        assert res.get_json()["roles"] == []

    def test_put_group_roles_invalid_role_id(self, client, app_context):
        """存在しないロールIDを指定した場合 404 が返ること。"""
        user = _create_user_with_perm("user:manage")
        _login(client, user)
        group = Group(name=f"grp-{uuid.uuid4().hex[:6]}")
        db.session.add(group)
        db.session.commit()

        res = client.put(
            f"/api/admin/groups/{group.id}/roles",
            json={"roleIds": [99999]},
        )
        assert res.status_code == 404
        assert res.get_json()["error"] == "role_not_found"

    def test_group_serialize_includes_roles(self, client, app_context):
        """グループ詳細レスポンスにロール情報が含まれること。"""
        user = _create_user_with_perm("user:manage")
        _login(client, user)
        role = Role(name=f"r-{uuid.uuid4().hex[:6]}")
        group = Group(name=f"grp-{uuid.uuid4().hex[:6]}")
        group.roles.append(role)
        db.session.add_all([role, group])
        db.session.commit()

        res = client.get(f"/api/admin/groups/{group.id}")
        assert res.status_code == 200
        data = res.get_json()
        assert "roles" in data["group"]
        assert any(r["id"] == role.id for r in data["group"]["roles"])
