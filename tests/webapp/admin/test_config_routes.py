import io
import json

import pytest

from webapp.services.system_setting_service import SystemSettingService


class _MockAdminUser:
    def __init__(self):
        self.is_authenticated = True

    def can(self, permission: str) -> bool:
        return permission == "system:manage"

    def get_id(self) -> str:
        return "admin"


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def test_export_config_excludes_hidden_keys(client, app_context, monkeypatch):
    admin = _MockAdminUser()
    monkeypatch.setattr("flask_login.utils._get_user", lambda: admin)

    with app_context.app_context():
        SystemSettingService.update_application_settings(
            {"SITE_NAME": "Example App", "JWT_SECRET_KEY": "top-secret"}
        )

    response = client.post("/admin/config", data={"action": "export-config"})

    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert "attachment;" in response.headers.get("Content-Disposition", "")

    payload = json.loads(response.data.decode("utf-8"))
    assert payload["version"] == 1
    assert payload["application"]["SITE_NAME"] == "Example App"
    assert "JWT_SECRET_KEY" not in payload["application"]


def test_import_config_updates_settings(client, app_context, monkeypatch):
    admin = _MockAdminUser()
    monkeypatch.setattr("flask_login.utils._get_user", lambda: admin)

    with app_context.app_context():
        SystemSettingService.update_application_settings(
            {
                "SITE_NAME": "Before Import",
                "SESSION_COOKIE_SECURE": False,
                "JWT_SECRET_KEY": "initial-secret",
            }
        )
        SystemSettingService.update_cors_settings({"allowedOrigins": ["https://before.example"]})

    payload = {
        "version": 1,
        "application": {
            "SITE_NAME": "After Import",
            "SESSION_COOKIE_SECURE": True,
        },
        "cors": {"allowedOrigins": ["https://after.example"]},
    }

    data = {
        "action": "import-config",
        "config_file": (io.BytesIO(json.dumps(payload).encode("utf-8")), "config.json"),
    }

    response = client.post(
        "/admin/config",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)

    with app_context.app_context():
        stored_application = SystemSettingService.load_application_config_payload()
        stored_cors = SystemSettingService.load_cors_config_payload()

    assert stored_application["SITE_NAME"] == "After Import"
    assert stored_application["SESSION_COOKIE_SECURE"] is True
    assert stored_application["JWT_SECRET_KEY"] == "initial-secret"
    assert stored_cors["allowedOrigins"] == ["https://after.example"]
