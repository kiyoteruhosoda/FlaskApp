import os
import json
import base64
import pytest

from core.crypto import encrypt
from core.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_CORS_SETTINGS,
)


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    key = base64.urlsafe_b64encode(b"0" * 32).decode()
    env = {
        "SECRET_KEY": "test",
        "DATABASE_URI": f"sqlite:///{db_path}",
        "GOOGLE_CLIENT_ID": "cid",
        "GOOGLE_CLIENT_SECRET": "sec",
        "ENCRYPTION_KEY": key,
    }
    prev = {k: os.environ.get(k) for k in env}
    os.environ.update(env)

    import importlib
    import webapp.config as config_module
    importlib.reload(config_module)
    import webapp as webapp_module
    importlib.reload(webapp_module)
    from webapp.config import BaseApplicationSettings
    BaseApplicationSettings.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app
    app = create_app()
    app.config.update(TESTING=True)
    from webapp.extensions import db
    from core.models.google_account import GoogleAccount
    from core.models.picker_session import PickerSession
    from webapp.services.system_setting_service import SystemSettingService
    from webapp import _apply_persisted_settings

    with app.app_context():
        db.create_all()
        payload = {
            key: app.config.get(key, DEFAULT_APPLICATION_SETTINGS.get(key))
            for key in DEFAULT_APPLICATION_SETTINGS
        }
        payload.update(
            {
                "SECRET_KEY": env["SECRET_KEY"],
                "GOOGLE_CLIENT_ID": env["GOOGLE_CLIENT_ID"],
                "GOOGLE_CLIENT_SECRET": env["GOOGLE_CLIENT_SECRET"],
                "ENCRYPTION_KEY": env["ENCRYPTION_KEY"],
            }
        )
        SystemSettingService.upsert_application_config(payload)
        SystemSettingService.upsert_cors_config(
            app.config.get("CORS_ALLOWED_ORIGINS", DEFAULT_CORS_SETTINGS.get("allowedOrigins", []))
        )
        _apply_persisted_settings(app)
        acc = GoogleAccount(
            email="g@example.com",
            scopes="",
            oauth_token_json=encrypt(json.dumps({"refresh_token": "r"})),
        )
        ps = PickerSession(account_id=1, status="pending")
        db.session.add_all([acc, ps])
        db.session.commit()
    yield app
    import sys
    del sys.modules["webapp.config"]
    del sys.modules["webapp"]
    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_exchange_refresh_token_invalid_grant(monkeypatch, app):
    import importlib
    mod = importlib.import_module("core.tasks.picker_import")
    class Resp:
        status_code = 401
        def json(self):
            return {"error": "invalid_grant"}
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp())
    from core.models.picker_session import PickerSession
    from core.models.google_account import GoogleAccount
    with app.app_context():
        ps = PickerSession.query.first()
        gacc = GoogleAccount.query.first()
        access, note = mod._exchange_refresh_token(gacc, ps)
        assert access is None
        assert note == "oauth_failed"
        assert ps.status == "failed"


def test_exchange_refresh_token_other_error(monkeypatch, app):
    import importlib
    mod = importlib.import_module("core.tasks.picker_import")
    class Resp:
        status_code = 500
        def json(self):
            return {"error": "server_error"}
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp())
    from core.models.picker_session import PickerSession
    from core.models.google_account import GoogleAccount
    with app.app_context():
        ps = PickerSession.query.first()
        gacc = GoogleAccount.query.first()
        access, note = mod._exchange_refresh_token(gacc, ps)
        assert access is None
        assert note == "oauth_error"
        assert ps.status == "error"
