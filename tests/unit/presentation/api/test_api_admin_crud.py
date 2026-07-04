"""管理 JSON API (roles / groups / permissions / service-accounts / dashboard) の単体テスト。"""
from __future__ import annotations

import uuid

import pytest

from shared.kernel.database.db import db
from shared.infrastructure.models.user import Permission, Role, User
from shared.infrastructure.models.group import Group


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _create_admin(app_context, *perm_codes: str) -> User:
    """指定の権限を持つ管理ユーザーを作成する。"""
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


# ---------------------------------------------------------------------------
# Admin Roles
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("app_context")
class TestAdminRolesApi:
    def test_list_roles_requires_user_manage(self, client, app_context):
        """権限なしでは 403 が返る。"""
        user = _create_admin(app_context)  # no permissions
        _login(client, user)
        res = client.get("/api/admin/roles")
        assert res.status_code == 403

    def test_list_roles_success(self, client, app_context):
        user = _create_admin(app_context, "user:manage")
        _login(client, user)
        res = client.get("/api/admin/roles")
        assert res.status_code == 200
        data = res.get_json()
        assert "roles" in data
        assert isinstance(data["roles"], list)

    def test_create_role(self, client, app_context):
        user = _create_admin(app_context, "user:manage")
        _login(client, user)
        res = client.post("/api/admin/roles", json={"name": "editor"})
        assert res.status_code == 201
        data = res.get_json()
        assert data["role"]["name"] == "editor"
        assert data["created"] is True

    def test_create_role_duplicate_name(self, client, app_context):
        user = _create_admin(app_context, "user:manage")
        _login(client, user)
        client.post("/api/admin/roles", json={"name": "dup-role"})
        res = client.post("/api/admin/roles", json={"name": "dup-role"})
        assert res.status_code == 409
        assert res.get_json()["error"] == "name_exists"

    def test_get_role_detail(self, client, app_context):
        user = _create_admin(app_context, "user:manage")
        _login(client, user)
        create_res = client.post("/api/admin/roles", json={"name": "detail-role"})
        role_id = create_res.get_json()["role"]["id"]

        res = client.get(f"/api/admin/roles/{role_id}")
        assert res.status_code == 200
        assert res.get_json()["role"]["name"] == "detail-role"

    def test_update_role(self, client, app_context):
        user = _create_admin(app_context, "user:manage")
        _login(client, user)
        create_res = client.post("/api/admin/roles", json={"name": "old-role"})
        role_id = create_res.get_json()["role"]["id"]

        res = client.put(f"/api/admin/roles/{role_id}", json={"name": "new-role"})
        assert res.status_code == 200
        assert res.get_json()["role"]["name"] == "new-role"

    def test_delete_role(self, client, app_context):
        user = _create_admin(app_context, "user:manage")
        _login(client, user)
        create_res = client.post("/api/admin/roles", json={"name": "to-delete"})
        role_id = create_res.get_json()["role"]["id"]

        res = client.delete(f"/api/admin/roles/{role_id}")
        assert res.status_code == 200
        assert res.get_json()["result"] == "deleted"

        get_res = client.get(f"/api/admin/roles/{role_id}")
        assert get_res.status_code == 404

    def test_default_role_flagged_and_immutable(self, client, app_context):
        """マスタデータのデフォルトロールは isDefault:true で編集・削除不可。"""
        user = _create_admin(app_context, "user:manage")
        _login(client, user)

        default_role = Role(name="admin")
        db.session.add(default_role)
        db.session.commit()

        res = client.get("/api/admin/roles")
        assert res.status_code == 200
        entries = {r["name"]: r for r in res.get_json()["roles"]}
        assert entries["admin"]["isDefault"] is True
        assert entries[user.roles[0].name]["isDefault"] is False

        update_res = client.put(
            f"/api/admin/roles/{default_role.id}", json={"name": "renamed"}
        )
        assert update_res.status_code == 403
        assert update_res.get_json()["error"] == "default_role_immutable"

        delete_res = client.delete(f"/api/admin/roles/{default_role.id}")
        assert delete_res.status_code == 403
        assert delete_res.get_json()["error"] == "default_role_immutable"


# ---------------------------------------------------------------------------
# Admin Permissions
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("app_context")
class TestAdminPermissionsApi:
    def test_list_permissions_requires_admin(self, client, app_context):
        user = _create_admin(app_context)
        _login(client, user)
        res = client.get("/api/admin/permissions")
        assert res.status_code == 403

    def test_list_permissions_success(self, client, app_context):
        user = _create_admin(app_context, "permission:manage")
        _login(client, user)
        res = client.get("/api/admin/permissions")
        assert res.status_code == 200
        assert "permissions" in res.get_json()

    def test_create_permission(self, client, app_context):
        user = _create_admin(app_context, "permission:manage")
        _login(client, user)
        res = client.post("/api/admin/permissions", json={"code": "test:action", "detail": "Test action"})
        assert res.status_code == 201
        data = res.get_json()
        assert data["permission"]["code"] == "test:action"
        assert data["permission"]["detail"] == "Test action"

    def test_create_permission_duplicate_code(self, client, app_context):
        user = _create_admin(app_context, "permission:manage")
        _login(client, user)
        client.post("/api/admin/permissions", json={"code": "dup:perm"})
        res = client.post("/api/admin/permissions", json={"code": "dup:perm"})
        assert res.status_code == 409
        assert res.get_json()["error"] == "code_exists"

    def test_update_permission(self, client, app_context):
        user = _create_admin(app_context, "permission:manage")
        _login(client, user)
        create_res = client.post("/api/admin/permissions", json={"code": "upd:perm"})
        perm_id = create_res.get_json()["permission"]["id"]

        res = client.put(f"/api/admin/permissions/{perm_id}", json={"detail": "Updated detail"})
        assert res.status_code == 200
        assert res.get_json()["permission"]["detail"] == "Updated detail"

    def test_delete_permission(self, client, app_context):
        user = _create_admin(app_context, "permission:manage")
        _login(client, user)
        create_res = client.post("/api/admin/permissions", json={"code": "del:perm"})
        perm_id = create_res.get_json()["permission"]["id"]

        res = client.delete(f"/api/admin/permissions/{perm_id}")
        assert res.status_code == 200
        assert res.get_json()["result"] == "deleted"

    def test_search_permissions(self, client, app_context):
        user = _create_admin(app_context, "permission:manage")
        _login(client, user)
        client.post("/api/admin/permissions", json={"code": "search:alpha"})
        client.post("/api/admin/permissions", json={"code": "search:beta"})
        client.post("/api/admin/permissions", json={"code": "other:gamma"})

        res = client.get("/api/admin/permissions?q=search")
        assert res.status_code == 200
        codes = [p["code"] for p in res.get_json()["permissions"]]
        assert all("search" in c for c in codes)


# ---------------------------------------------------------------------------
# Admin Groups
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("app_context")
class TestAdminGroupsApi:
    def test_list_groups_requires_user_manage(self, client, app_context):
        user = _create_admin(app_context)
        _login(client, user)
        res = client.get("/api/admin/groups")
        assert res.status_code == 403

    def test_list_and_create_group(self, client, app_context):
        user = _create_admin(app_context, "user:manage")
        _login(client, user)

        create_res = client.post(
            "/api/admin/groups",
            json={"name": "Engineering", "description": "Engineers"},
        )
        assert create_res.status_code == 201
        group_id = create_res.get_json()["group"]["id"]

        list_res = client.get("/api/admin/groups")
        assert list_res.status_code == 200
        ids = [g["id"] for g in list_res.get_json()["groups"]]
        assert group_id in ids

    def test_create_group_with_parent(self, client, app_context):
        user = _create_admin(app_context, "user:manage")
        _login(client, user)

        parent_res = client.post("/api/admin/groups", json={"name": "Parent"})
        parent_id = parent_res.get_json()["group"]["id"]

        child_res = client.post(
            "/api/admin/groups",
            json={"name": "Child", "parentId": parent_id},
        )
        assert child_res.status_code == 201
        child = child_res.get_json()["group"]
        assert child["parentId"] == parent_id
        assert child["parentName"] == "Parent"

    def test_update_group(self, client, app_context):
        user = _create_admin(app_context, "user:manage")
        _login(client, user)

        create_res = client.post("/api/admin/groups", json={"name": "OldName"})
        group_id = create_res.get_json()["group"]["id"]

        update_res = client.put(
            f"/api/admin/groups/{group_id}",
            json={"name": "NewName", "description": "Updated"},
        )
        assert update_res.status_code == 200
        assert update_res.get_json()["group"]["name"] == "NewName"

    def test_delete_group(self, client, app_context):
        user = _create_admin(app_context, "user:manage")
        _login(client, user)

        create_res = client.post("/api/admin/groups", json={"name": "ToDelete"})
        group_id = create_res.get_json()["group"]["id"]

        res = client.delete(f"/api/admin/groups/{group_id}")
        assert res.status_code == 200

    def test_delete_group_with_children_fails(self, client, app_context):
        user = _create_admin(app_context, "user:manage")
        _login(client, user)

        parent_res = client.post("/api/admin/groups", json={"name": "ParentGroup"})
        parent_id = parent_res.get_json()["group"]["id"]
        client.post("/api/admin/groups", json={"name": "ChildGroup", "parentId": parent_id})

        res = client.delete(f"/api/admin/groups/{parent_id}")
        assert res.status_code == 400
        assert res.get_json()["error"] == "has_children"


# ---------------------------------------------------------------------------
# Admin Service Accounts
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("app_context")
class TestAdminServiceAccountsApi:
    def test_list_requires_system_settings(self, client, app_context):
        user = _create_admin(app_context)
        _login(client, user)
        res = client.get("/api/admin/service-accounts")
        assert res.status_code == 403

    def test_create_and_list(self, client, app_context):
        user = _create_admin(app_context, "service_account:manage")
        _login(client, user)

        create_res = client.post(
            "/api/admin/service-accounts",
            json={"name": "backup-bot", "scopes": ["media:view"], "isActive": True},
        )
        assert create_res.status_code == 201
        sa = create_res.get_json()["serviceAccount"]
        assert sa["name"] == "backup-bot"
        assert "media:view" in sa["scopes"]

        list_res = client.get("/api/admin/service-accounts")
        assert list_res.status_code == 200
        names = [a["name"] for a in list_res.get_json()["serviceAccounts"]]
        assert "backup-bot" in names

    def test_update_service_account(self, client, app_context):
        user = _create_admin(app_context, "service_account:manage")
        _login(client, user)

        create_res = client.post("/api/admin/service-accounts", json={"name": "old-bot"})
        sa_id = create_res.get_json()["serviceAccount"]["id"]

        update_res = client.put(
            f"/api/admin/service-accounts/{sa_id}",
            json={"name": "new-bot", "isActive": False},
        )
        assert update_res.status_code == 200
        updated = update_res.get_json()["serviceAccount"]
        assert updated["name"] == "new-bot"
        assert updated["isActive"] is False

    def test_delete_service_account(self, client, app_context):
        user = _create_admin(app_context, "service_account:manage")
        _login(client, user)

        create_res = client.post("/api/admin/service-accounts", json={"name": "to-del-bot"})
        sa_id = create_res.get_json()["serviceAccount"]["id"]

        res = client.delete(f"/api/admin/service-accounts/{sa_id}")
        assert res.status_code == 200
        assert res.get_json()["result"] == "deleted"


# ---------------------------------------------------------------------------
# Admin Dashboard
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("app_context")
class TestAdminDashboardApi:
    def test_dashboard_requires_system_settings(self, client, app_context):
        user = _create_admin(app_context)
        _login(client, user)
        res = client.get("/api/admin/dashboard")
        assert res.status_code == 403

    def test_dashboard_returns_stats(self, client, app_context):
        user = _create_admin(app_context, "admin:system-settings")
        _login(client, user)
        res = client.get("/api/admin/dashboard")
        assert res.status_code == 200
        data = res.get_json()
        assert "stats" in data
        stats = data["stats"]
        assert "users" in stats
        assert "total" in stats["users"]
        assert "active" in stats["users"]
        assert "roles" in stats
        assert "groups" in stats
        assert "recentJobs" in stats
