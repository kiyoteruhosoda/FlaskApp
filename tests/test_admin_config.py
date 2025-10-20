import json

import pytest

from core.models.user import User, Role, Permission
from core.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS
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
    SystemSettingService.update_application_settings({"FEATURE_FLAG": True})
    SystemSettingService.update_cors_settings({"allowedOrigins": ["https://example.com"]})

    user = _create_system_manager()
    _login(client, user)

    response = client.get("/admin/config")
    assert response.status_code == 200

    html = response.data.decode("utf-8")
    assert 'name="app_config_new[FEATURE_FLAG]"' in html
    assert 'name="cors_new[allowedOrigins]"' in html
    assert "https://example.com" in html


def test_update_application_config_field_success(client):
    user = _create_system_manager()
    _login(client, user)

    response = client.post(
        "/admin/config",
        data={
            "action": "update-app-config-fields",
            "app_config_selected": ["UPLOAD_MAX_SIZE"],
            "app_config_new[UPLOAD_MAX_SIZE]": "2048",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Application configuration updated." in html

    config = SystemSettingService.load_application_config()
    assert config["UPLOAD_MAX_SIZE"] == 2048


def test_update_application_config_rejects_empty_required(client):
    user = _create_system_manager()
    _login(client, user)

    original_value = SystemSettingService.load_application_config()["JWT_SECRET_KEY"]

    response = client.post(
        "/admin/config",
        data={
            "action": "update-app-config-fields",
            "app_config_selected": ["JWT_SECRET_KEY"],
            "app_config_new[JWT_SECRET_KEY]": "",
        },
    )

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Value for JWT secret key is required." in html

    config = SystemSettingService.load_application_config()
    assert config["JWT_SECRET_KEY"] == original_value


def test_update_application_config_revert_to_default(client):
    SystemSettingService.update_application_settings({"TRANSCODE_CRF": 18})

    user = _create_system_manager()
    _login(client, user)

    response = client.post(
        "/admin/config",
        data={
            "action": "update-app-config-fields",
            "app_config_selected": ["TRANSCODE_CRF"],
            "app_config_use_default[TRANSCODE_CRF]": "1",
            "app_config_new[TRANSCODE_CRF]": "12",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Application configuration updated." in html

    config = SystemSettingService.load_application_config()
    assert config["TRANSCODE_CRF"] == DEFAULT_APPLICATION_SETTINGS["TRANSCODE_CRF"]


def test_update_cors_config_success(client):
    user = _create_system_manager()
    _login(client, user)

    response = client.post(
        "/admin/config",
        data={
            "action": "update-cors",
            "cors_selected": ["allowedOrigins"],
            "cors_new[allowedOrigins]": "https://admin.example.com\nhttps://app.example.com",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "CORS allowed origins updated." in html

    assert client.application.config["CORS_ALLOWED_ORIGINS"] == (
        "https://admin.example.com",
        "https://app.example.com",
    )

    config = SystemSettingService.load_cors_config()
    assert config["allowedOrigins"] == [
        "https://admin.example.com",
        "https://app.example.com",
    ]


def test_update_cors_config_rejects_invalid_origin(client):
    SystemSettingService.update_cors_settings({"allowedOrigins": ["https://existing.example.com"]})
    user = _create_system_manager()
    _login(client, user)

    response = client.post(
        "/admin/config",
        data={
            "action": "update-cors",
            "cors_selected": ["allowedOrigins"],
            "cors_new[allowedOrigins]": "example.com\nhttps://valid.example.com",
        },
    )

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Invalid values" in html

    config = SystemSettingService.load_cors_config()
    assert config["allowedOrigins"] == ["https://existing.example.com"]
