import json

import pytest

from core.models.user import User, Role, Permission
from webapp.extensions import db
from webapp.services.system_setting_service import SystemSettingService


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def _login(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def _create_system_manager():
    manage_permission = Permission(code="system:manage")
    admin_role = Role(name="admin")
    admin_role.permissions.append(manage_permission)
    user = User(email="admin@example.com")
    user.set_password("secret")
    user.roles.append(admin_role)
    db.session.add_all([manage_permission, admin_role, user])
    db.session.commit()
    return user


def test_config_page_requires_permission(client):
    user = User(email="user@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    _login(client, user)

    response = client.get("/admin/config")
    assert response.status_code == 403


def test_config_page_displays_current_settings(client):
    SystemSettingService.upsert_application_config({"FEATURE_FLAG": True})
    SystemSettingService.upsert_cors_config(["https://example.com"])

    user = _create_system_manager()
    _login(client, user)

    response = client.get("/admin/config")
    assert response.status_code == 200

    html = response.data.decode("utf-8")
    assert "FEATURE_FLAG" in html
    assert "https://example.com" in html


def test_update_application_config_valid_json(client):
    user = _create_system_manager()
    _login(client, user)

    payload = {"CUSTOM_VALUE": 123, "FEATURE_FLAG": False}
    response = client.post(
        "/admin/config",
        data={
            "action": "update-app-config",
            "app_config_json": json.dumps(payload),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Application configuration updated." in html

    config = SystemSettingService.load_application_config()
    assert config["CUSTOM_VALUE"] == 123
    assert config["FEATURE_FLAG"] is False


def test_update_application_config_invalid_json_shows_error(client):
    SystemSettingService.upsert_application_config({"KEEP_ME": "original"})
    user = _create_system_manager()
    _login(client, user)

    response = client.post(
        "/admin/config",
        data={
            "action": "update-app-config",
            "app_config_json": "{invalid}",
        },
    )

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Failed to parse application configuration JSON" in html

    config = SystemSettingService.load_application_config()
    assert config["KEEP_ME"] == "original"


def test_update_cors_config_success(client):
    user = _create_system_manager()
    _login(client, user)

    response = client.post(
        "/admin/config",
        data={
            "action": "update-cors",
            "allowed_origins": "https://admin.example.com\nhttps://app.example.com",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "CORS allowed origins updated." in html

    config = SystemSettingService.load_cors_config()
    assert config["allowedOrigins"] == [
        "https://admin.example.com",
        "https://app.example.com",
    ]


def test_update_cors_config_rejects_invalid_origin(client):
    SystemSettingService.upsert_cors_config(["https://existing.example.com"])
    user = _create_system_manager()
    _login(client, user)

    response = client.post(
        "/admin/config",
        data={
            "action": "update-cors",
            "allowed_origins": "example.com\nhttps://valid.example.com",
        },
    )

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Invalid values" in html

    config = SystemSettingService.load_cors_config()
    assert config["allowedOrigins"] == ["https://existing.example.com"]
