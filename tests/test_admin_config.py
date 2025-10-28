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


def test_config_update_requires_login_returns_json(client):
    app = client.application
    original_testing = app.config.get("TESTING")
    original_login_disabled = app.config.get("LOGIN_DISABLED")
    app.config["TESTING"] = False
    app.config["LOGIN_DISABLED"] = False

    try:
        response = client.post(
            "/admin/config",
            data={"action": "update-app-config-fields"},
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            },
        )
    finally:
        if original_testing is None:
            app.config.pop("TESTING", None)
        else:
            app.config["TESTING"] = original_testing

        if original_login_disabled is None:
            app.config.pop("LOGIN_DISABLED", None)
        else:
            app.config["LOGIN_DISABLED"] = original_login_disabled

    assert response.status_code == 401
    payload = response.get_json()
    assert payload["error"] == "unauthorized"
    assert payload["login_state"] == "session_cookie_missing"
    assert payload["message"] == "Please log in to access this page."
    assert response.headers["X-Session-Expired"] == "1"


def test_config_page_displays_current_settings(client):
    SystemSettingService.update_application_settings({"FEATURE_FLAG": True})
    SystemSettingService.update_cors_settings({"allowedOrigins": ["https://example.com"]})
    from webapp import _apply_persisted_settings

    _apply_persisted_settings(client.application)

    user = _create_system_manager()
    _login(client, user)

    response = client.get("/admin/config")
    assert response.status_code == 200

    html = response.data.decode("utf-8")
    assert 'name="app_config_new[FEATURE_FLAG]"' in html
    assert 'name="cors_new[allowedOrigins]"' in html
    assert 'name="cors_new[CORS_ALLOWED_ORIGINS]"' not in html
    assert "Updated automatically after saving allowedOrigins." in html
    assert "https://example.com" in html
    assert 'data-cors-effective' in html
    assert 'data-cors-key="allowedOrigins"' in html
    assert 'data-app-key="CORS_ALLOWED_ORIGINS"' not in html


def test_update_application_config_field_success(client):
    user = _create_system_manager()
    _login(client, user)

    response = client.post(
        "/admin/config",
        data={
            "action": "update-app-config-fields",
            "app_config_selected": ["MEDIA_UPLOAD_MAX_SIZE_BYTES"],
            "app_config_new[MEDIA_UPLOAD_MAX_SIZE_BYTES]": "2048",
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert "Application configuration updated." in payload["message"]
    assert payload["action"] == "update-app-config-fields"
    assert client.application.config["MEDIA_UPLOAD_MAX_SIZE_BYTES"] == 2048

    config = SystemSettingService.load_application_config()
    assert config["MEDIA_UPLOAD_MAX_SIZE_BYTES"] == 2048


def test_update_application_config_rejects_empty_required(client):
    user = _create_system_manager()
    _login(client, user)

    original_value = SystemSettingService.load_application_config()["ACCESS_TOKEN_ISSUER"]

    response = client.post(
        "/admin/config",
        data={
            "action": "update-app-config-fields",
            "app_config_selected": ["ACCESS_TOKEN_ISSUER"],
            "app_config_new[ACCESS_TOKEN_ISSUER]": "",
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["status"] == "error"
    assert "Value for Access token issuer is required." in payload["message"]

    config = SystemSettingService.load_application_config()
    assert config["ACCESS_TOKEN_ISSUER"] == original_value


def test_update_application_config_rejects_readonly_field(client):
    user = _create_system_manager()
    _login(client, user)

    original_value = client.application.config.get("SQLALCHEMY_DATABASE_URI")
    assert original_value is not None

    response = client.post(
        "/admin/config",
        data={
            "action": "update-app-config-fields",
            "app_config_selected": ["SQLALCHEMY_DATABASE_URI"],
            "app_config_new[SQLALCHEMY_DATABASE_URI]": "sqlite:///mutated.db",
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["status"] == "error"
    assert "SQLAlchemy database URI is read-only" in payload["message"]

    config = SystemSettingService.load_application_config()
    assert "SQLALCHEMY_DATABASE_URI" not in config
    assert client.application.config["SQLALCHEMY_DATABASE_URI"] == original_value


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
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert "Application configuration updated." in payload["message"]

    config = SystemSettingService.load_application_config()
    assert config["TRANSCODE_CRF"] == DEFAULT_APPLICATION_SETTINGS["TRANSCODE_CRF"]


def test_update_application_config_triggers_relogin_warning(client):
    user = _create_system_manager()
    _login(client, user)

    response = client.post(
        "/admin/config",
        data={
            "action": "update-app-config-fields",
            "app_config_selected": ["SECRET_KEY"],
            "app_config_new[SECRET_KEY]": "new-secret-key",
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert "Application configuration updated." in payload["message"]
    assert "Changes to Flask secret key require all users to sign in again." in payload["warnings"][0]
    assert client.application.config["SECRET_KEY"] == "new-secret-key"

    config = SystemSettingService.load_application_config()
    assert config["SECRET_KEY"] == "new-secret-key"


def test_update_signing_requires_secret_for_builtin(client):
    user = _create_system_manager()
    _login(client, user)

    original_secret = SystemSettingService.load_application_config()["JWT_SECRET_KEY"]

    response = client.post(
        "/admin/config",
        data={
            "action": "update-signing",
            "access_token_signing": "builtin",
            "builtin_secret": "",
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["status"] == "error"
    assert "Please provide a JWT secret key for built-in signing." in payload["message"]

    config = SystemSettingService.load_application_config()
    assert config["JWT_SECRET_KEY"] == original_secret


def test_update_signing_builtin_updates_secret(client):
    user = _create_system_manager()
    _login(client, user)

    response = client.post(
        "/admin/config",
        data={
            "action": "update-signing",
            "access_token_signing": "builtin",
            "builtin_secret": "new-built-in-secret",
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert "Access token signing will use the built-in secret." in payload["message"]

    config = SystemSettingService.load_application_config()
    assert config["JWT_SECRET_KEY"] == "new-built-in-secret"
    assert client.application.config["JWT_SECRET_KEY"] == "new-built-in-secret"


def test_update_cors_config_success(client):
    user = _create_system_manager()
    _login(client, user)

    response = client.post(
        "/admin/config",
        data={
            "action": "update-cors",
            "cors_new[allowedOrigins]": "https://admin.example.com\nhttps://app.example.com",
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    assert "CORS allowed origins updated." in payload["message"]

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
            "cors_new[allowedOrigins]": "example.com\nhttps://valid.example.com",
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["status"] == "error"
    assert "Invalid values" in payload["message"]

    config = SystemSettingService.load_cors_config()
    assert config["allowedOrigins"] == ["https://existing.example.com"]
