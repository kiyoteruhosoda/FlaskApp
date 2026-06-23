"""Tests for profile role switching functionality."""

import uuid
import pytest
from flask import session

from shared.infrastructure.models.user import User, Role, Permission
from presentation.web.bootstrap.extensions import db


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def _create_user_with_roles_and_permissions(email, password):
    """Create a user with two roles that have different permissions."""
    user = User(email=email)
    user.set_password(password)
    
    # Create manager role with manager permissions
    manager_role = Role(name="manager")
    manager_perm1 = Permission(code="media:manage")
    manager_perm2 = Permission(code="album:manage")
    dashboard_perm = Permission(code="dashboard:view")
    db.session.add(manager_perm1)
    db.session.add(manager_perm2)
    db.session.add(dashboard_perm)
    manager_role.permissions.extend([manager_perm1, manager_perm2, dashboard_perm])
    db.session.add(manager_role)
    
    # Create viewer role with only view permissions
    viewer_role = Role(name="viewer")
    viewer_perm = Permission(code="media:view")
    db.session.add(viewer_perm)
    viewer_role.permissions.extend([viewer_perm, dashboard_perm])
    db.session.add(viewer_role)
    
    # Assign both roles to user
    user.roles.extend([manager_role, viewer_role])
    db.session.add(user)
    db.session.commit()
    
    return user, manager_role, viewer_role


def _login(client, email, password):
    """Helper to login a user."""
    response = client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )
    return response


def _active_permissions_via_api(client):
    """``GET /api/auth/me`` からアクティブロールの権限集合を取得する。"""
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    active_role = me.get_json()["active_role"]
    assert active_role is not None
    return active_role, set(active_role["permissions"])


def test_profile_role_switch_updates_permissions(client):
    """ロール切替でアクティブ権限が更新されること。

    プロフィール画面・ロール切替 UI は React SPA が描画するため、SPA が利用する
    ``POST /api/auth/select-role`` と ``GET /api/auth/me`` の active_role で検証する。
    """
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"

    user, manager_role, viewer_role = _create_user_with_roles_and_permissions(email, password)
    manager_id, viewer_id = manager_role.id, viewer_role.id

    # Login（複数ロールのためロール選択が要求される）
    login = client.post("/api/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    assert login.get_json()["requires_role_selection"] is True

    # Select manager role
    response = client.post("/api/auth/select-role", json={"role_id": manager_id})
    assert response.status_code == 200

    active_role, manager_perms = _active_permissions_via_api(client)
    assert active_role["name"] == "manager"
    assert "media:manage" in manager_perms
    assert "album:manage" in manager_perms

    # Now switch to viewer role
    response = client.post("/api/auth/select-role", json={"role_id": viewer_id})
    assert response.status_code == 200
    assert response.get_json()["active_role"]["name"] == "viewer"

    active_role, viewer_perms = _active_permissions_via_api(client)
    assert active_role["name"] == "viewer"
    assert "media:view" in viewer_perms
    assert "media:manage" not in viewer_perms
    assert "album:manage" not in viewer_perms


def test_profile_role_switch_persists_across_requests(client):
    """ロール切替がセッションを跨いで維持されること。"""
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"

    user, manager_role, viewer_role = _create_user_with_roles_and_permissions(email, password)
    manager_id, viewer_id = manager_role.id, viewer_role.id

    # Login and select manager role
    client.post("/api/auth/login", json={"email": email, "password": password})
    client.post("/api/auth/select-role", json={"role_id": manager_id})

    _, manager_perms = _active_permissions_via_api(client)
    assert "media:manage" in manager_perms

    # Switch to viewer role
    client.post("/api/auth/select-role", json={"role_id": viewer_id})

    # Make another request to verify the role persists
    _, viewer_perms = _active_permissions_via_api(client)
    assert "media:view" in viewer_perms
    assert "media:manage" not in viewer_perms

    with client.session_transaction() as sess:
        assert sess["active_role_id"] == viewer_id


def test_current_user_can_method_respects_active_role(client):
    """Test that current_user.can() method respects the active role."""
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"
    
    user, manager_role, viewer_role = _create_user_with_roles_and_permissions(email, password)
    
    # Login and select viewer role
    _login(client, email, password)
    client.post("/auth/select-role", data={"active_role": str(viewer_role.id)})
    
    # Make a request that would check permissions
    with client.application.test_request_context():
        from flask_login import login_user
        from presentation.web.services.token_service import TokenService
        
        # Simulate loading the user as the login system does
        with client.session_transaction() as sess:
            active_role_id = sess.get("active_role_id")
            assert active_role_id == viewer_role.id
        
        # Create principal with active role
        principal = TokenService.create_principal_for_user(user, active_role_id=viewer_role.id)
        
        # Verify permissions
        assert principal.can("media:view") is True
        assert principal.can("media:manage") is False
        assert principal.can("album:manage") is False


def test_invalid_role_switch_shows_error(client):
    """無効なロールへの切替がエラーになり、元のロールが維持されること。"""
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"

    user, manager_role, viewer_role = _create_user_with_roles_and_permissions(email, password)
    manager_id = manager_role.id

    # Login and select manager role
    client.post("/api/auth/login", json={"email": email, "password": password})
    client.post("/api/auth/select-role", json={"role_id": manager_id})

    # Try to switch to a non-existent role
    response = client.post("/api/auth/select-role", json={"role_id": 99999})
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_role"

    # Verify the original role is still active
    active_role, manager_perms = _active_permissions_via_api(client)
    assert active_role["id"] == manager_id
    assert "media:manage" in manager_perms
