"""管理 JSON API — アプリケーション設定 (/api/admin/config) の単体テスト。"""
from __future__ import annotations

import uuid

import pytest

from shared.kernel.database.db import db
from shared.infrastructure.models.user import Permission, Role, User
from presentation.web.services.system_setting_service import SystemSettingService


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _create_user(*perm_codes: str) -> User:
    perms = [Permission(code=code) for code in perm_codes]
    for p in perms:
        db.session.add(p)
    role = Role(name=f"role-{uuid.uuid4().hex[:6]}")
    role.permissions = perms
    db.session.add(role)
    user = User(email=f"u-{uuid.uuid4().hex[:8]}@example.com")
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
# GET /api/admin/config
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("app_context")
class TestAdminConfigGet:
    def test_requires_system_manage(self, client, app_context):
        user = _create_user("media:view")  # wrong permission
        _login(client, user)
        res = client.get("/api/admin/config")
        assert res.status_code == 403

    def test_returns_sections_and_fields(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.get("/api/admin/config")
        assert res.status_code == 200
        data = res.get_json()
        assert "application_sections" in data
        assert "application_fields" in data
        assert "cors_fields" in data
        assert "signingGroups" in data
        assert isinstance(data["application_sections"], list)
        # known section present
        identifiers = {s["identifier"] for s in data["application_sections"]}
        assert "security" in identifiers

    def test_field_has_expected_shape(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.get("/api/admin/config")
        fields = res.get_json()["application_fields"]
        assert fields
        field = fields[0]
        for key in ("key", "label", "data_type", "editable", "form_value", "section"):
            assert key in field


# ---------------------------------------------------------------------------
# PUT /api/admin/config
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("app_context")
class TestAdminConfigUpdate:
    def test_requires_system_manage(self, client, app_context):
        user = _create_user("user:manage")
        _login(client, user)
        res = client.put("/api/admin/config", json={"updates": {"TRANSCODE_CRF": 20}})
        assert res.status_code == 403

    def test_no_changes_returns_400(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config", json={})
        assert res.status_code == 400
        assert res.get_json()["error"] == "no_changes"

    def test_update_integer_setting(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config", json={"updates": {"TRANSCODE_CRF": 18}})
        assert res.status_code == 200
        assert res.get_json()["updated"] is True
        payload = SystemSettingService.load_application_config_payload()
        assert payload["TRANSCODE_CRF"] == 18

    def test_update_boolean_setting(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config", json={"updates": {"MAIL_ENABLED": True}})
        assert res.status_code == 200
        payload = SystemSettingService.load_application_config_payload()
        assert payload["MAIL_ENABLED"] is True

    def test_update_invalid_integer_returns_validation_error(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config", json={"updates": {"TRANSCODE_CRF": "not-a-number"}})
        assert res.status_code == 400
        assert res.get_json()["error"] == "validation_error"

    def test_update_unknown_key_returns_error(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config", json={"updates": {"NOPE_UNKNOWN": "x"}})
        assert res.status_code == 400
        assert res.get_json()["error"] == "validation_error"

    def test_readonly_key_rejected(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config", json={"updates": {"SQLALCHEMY_DATABASE_URI": "sqlite://"}})
        assert res.status_code == 400

    def test_hidden_key_rejected(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config", json={"updates": {"JWT_SECRET_KEY": "leak"}})
        assert res.status_code == 400

    def test_reset_key_removes_override(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        # set then reset
        client.put("/api/admin/config", json={"updates": {"TRANSCODE_CRF": 30}})
        assert SystemSettingService.load_application_config_payload().get("TRANSCODE_CRF") == 30
        res = client.put("/api/admin/config", json={"resetKeys": ["TRANSCODE_CRF"]})
        assert res.status_code == 200
        assert "TRANSCODE_CRF" not in SystemSettingService.load_application_config_payload()


# ---------------------------------------------------------------------------
# PUT /api/admin/config/cors
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("app_context")
class TestAdminConfigCors:
    def test_requires_system_manage(self, client, app_context):
        user = _create_user("media:view")
        _login(client, user)
        res = client.put("/api/admin/config/cors", json={"allowedOrigins": ["https://x.com"]})
        assert res.status_code == 403

    def test_update_cors_origins(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config/cors", json={"allowedOrigins": ["https://app.example.com"]})
        assert res.status_code == 200
        payload = SystemSettingService.load_cors_config_payload()
        assert "https://app.example.com" in payload["allowedOrigins"]

    def test_invalid_origin_rejected(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config/cors", json={"allowedOrigins": ["not-a-url"]})
        assert res.status_code == 400
        assert res.get_json()["error"] == "validation_error"

    def test_wildcard_origin_allowed(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config/cors", json={"allowedOrigins": ["*"]})
        assert res.status_code == 200

    def test_cors_must_be_array(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config/cors", json={"allowedOrigins": "https://x.com"})
        assert res.status_code == 400
        assert res.get_json()["error"] == "invalid_body"


# ---------------------------------------------------------------------------
# PUT /api/admin/config/signing
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("app_context")
class TestAdminConfigSigning:
    def test_requires_system_manage(self, client, app_context):
        user = _create_user("user:manage")
        _login(client, user)
        res = client.put("/api/admin/config/signing", json={"mode": "builtin", "secret": "x"})
        assert res.status_code == 403

    def test_builtin_requires_secret(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config/signing", json={"mode": "builtin", "secret": ""})
        assert res.status_code == 400
        assert res.get_json()["error"] == "validation_error"

    def test_builtin_with_secret(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config/signing", json={"mode": "builtin", "secret": "super-secret-key"})
        assert res.status_code == 200
        assert res.get_json()["updated"] is True
        setting = SystemSettingService.get_access_token_signing_setting()
        assert setting.mode == "builtin"

    def test_unsupported_mode_rejected(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config/signing", json={"mode": "weird"})
        assert res.status_code == 400

    def test_server_signing_requires_group(self, client, app_context):
        user = _create_user("system:manage")
        _login(client, user)
        res = client.put("/api/admin/config/signing", json={"mode": "server_signing", "groupCode": ""})
        assert res.status_code == 400
        assert res.get_json()["error"] == "validation_error"
