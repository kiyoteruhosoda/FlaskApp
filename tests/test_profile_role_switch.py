"""Tests for profile role switching functionality."""

import uuid
import pytest
from flask import session

from core.models.user import User, Role, Permission
from webapp.extensions import db


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


def test_profile_role_switch_updates_permissions(client):
    """Test that switching roles in profile updates the active permissions."""
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"
    
    user, manager_role, viewer_role = _create_user_with_roles_and_permissions(email, password)
    
    # Login
    response = _login(client, email, password)
    assert response.status_code in (302, 303)
    
    # Should redirect to role selection
    assert "/auth/select-role" in response.headers["Location"]
    
    # Select manager role
    response = client.post(
        "/auth/select-role",
        data={"active_role": str(manager_role.id)},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    
    # Check profile shows manager permissions
    response = client.get("/auth/profile")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    
    # Extract the Active permissions section
    import re
    active_perms_match = re.search(
        r'<h2[^>]*>Active permissions</h2>.*?<div[^>]*class="d-flex[^"]*"[^>]*>(.*?)</div>',
        html,
        re.DOTALL
    )
    assert active_perms_match is not None, "Could not find Active permissions section"
    active_perms_section = active_perms_match.group(1)
    
    # Should show manager permissions in the active permissions section
    assert "media:manage" in active_perms_section
    assert "album:manage" in active_perms_section
    
    # Now switch to viewer role
    response = client.post(
        "/auth/profile",
        data={"action": "switch-role", "active_role": str(viewer_role.id)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    
    # Check the flash message
    html = response.data.decode("utf-8")
    assert "Active role switched to viewer" in html
    
    # Extract the Active permissions section to verify it shows only viewer permissions
    import re
    active_perms_match = re.search(
        r'<h2[^>]*>Active permissions</h2>.*?<div[^>]*class="d-flex[^"]*"[^>]*>(.*?)</div>',
        html,
        re.DOTALL
    )
    assert active_perms_match is not None, "Could not find Active permissions section"
    active_perms_section = active_perms_match.group(1)
    
    # Check permissions are now limited to viewer role
    assert "media:view" in active_perms_section
    # Should NOT show manager permissions in the active permissions section
    assert "media:manage" not in active_perms_section
    assert "album:manage" not in active_perms_section


def test_profile_role_switch_persists_across_requests(client):
    """Test that role switch persists in session across multiple requests."""
    import re
    
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"
    
    user, manager_role, viewer_role = _create_user_with_roles_and_permissions(email, password)
    
    # Login and select manager role
    _login(client, email, password)
    client.post("/auth/select-role", data={"active_role": str(manager_role.id)})
    
    # Verify manager permissions
    response = client.get("/auth/profile")
    html = response.data.decode("utf-8")
    active_perms_match = re.search(
        r'<h2[^>]*>Active permissions</h2>.*?<div[^>]*class="d-flex[^"]*"[^>]*>(.*?)</div>',
        html,
        re.DOTALL
    )
    assert active_perms_match is not None
    assert "media:manage" in active_perms_match.group(1)
    
    # Switch to viewer role
    client.post(
        "/auth/profile",
        data={"action": "switch-role", "active_role": str(viewer_role.id)},
    )
    
    # Make another request to verify the role persists
    response = client.get("/auth/profile")
    html = response.data.decode("utf-8")
    active_perms_match = re.search(
        r'<h2[^>]*>Active permissions</h2>.*?<div[^>]*class="d-flex[^"]*"[^>]*>(.*?)</div>',
        html,
        re.DOTALL
    )
    assert active_perms_match is not None
    active_perms_section = active_perms_match.group(1)
    assert "media:view" in active_perms_section
    assert "media:manage" not in active_perms_section
    
    # Verify via dashboard or any other route
    response = client.get("/dashboard/")
    assert response.status_code == 200


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
        from webapp.services.token_service import TokenService
        
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
    """Test that switching to an invalid role shows an error."""
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    password = "password123"
    
    user, manager_role, viewer_role = _create_user_with_roles_and_permissions(email, password)
    
    # Login and select manager role
    _login(client, email, password)
    client.post("/auth/select-role", data={"active_role": str(manager_role.id)})
    
    # Try to switch to a non-existent role
    response = client.post(
        "/auth/profile",
        data={"action": "switch-role", "active_role": "99999"},
        follow_redirects=True,
    )
    
    html = response.data.decode("utf-8")
    assert "Invalid role selection" in html
    
    # Verify the original role is still active
    response = client.get("/auth/profile")
    html = response.data.decode("utf-8")
    assert "media:manage" in html
