import base64
import hashlib
import importlib
import json
import os
import sys

import pytest
from flask import request, session as flask_session


@pytest.fixture
def app(tmp_path):
    # テスト専用の環境変数を設定
    thumbs = tmp_path / "thumbs"
    play = tmp_path / "play"
    thumbs.mkdir()
    play.mkdir()
    
    # 環境変数をクリア（.envファイルの設定を無効化）
    test_env_vars = {
        "SECRET_KEY": "test-secret-key",
        "JWT_SECRET_KEY": "test-jwt-secret",
        "DATABASE_URI": "sqlite:///:memory:",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "OAUTH_TOKEN_KEY": base64.urlsafe_b64encode(b"0" * 32).decode(),
        "FPV_DL_SIGN_KEY": base64.urlsafe_b64encode(b"1" * 32).decode(),
        "FPV_URL_TTL_THUMB": "600",
        "FPV_URL_TTL_PLAYBACK": "600",
        "FPV_NAS_THUMBS_DIR": str(thumbs),
        "FPV_NAS_PLAY_DIR": str(play),
    }
    
    # 既存の環境変数を保存
    original_env = {}
    for key, value in test_env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    try:
        # configモジュールをリロードして新しい環境変数を反映
        import webapp.config as config_module
        importlib.reload(config_module)
        import webapp as webapp_module
        importlib.reload(webapp_module)
        
        from webapp import create_app
        from webapp.config import TestConfig

        app = create_app()
        app.config.from_object(TestConfig)

        from webapp.extensions import db

        with app.app_context():
            db.create_all()

            @app.route("/boom")
            def boom():
                raise Exception("boom")

            @app.route("/bad")
            def bad():
                return "bad", 502

            @app.post("/api/ping")
            def api_ping():
                body = request.get_json(silent=True) or {}
                return {"ok": True, "access_token": "real-token", "echo": body}

            @app.post("/api/form")
            def api_form():
                return {"ok": True, "refresh_token": "form-token"}

        yield app

    finally:
        # 環境変数を元に戻す
        for key, original_value in original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
        
        # モジュールをクリーンアップ
        if "webapp.config" in sys.modules:
            del sys.modules["webapp.config"]
        if "webapp" in sys.modules:
            del sys.modules["webapp"]


@pytest.fixture
def client(app):
    return app.test_client()


def test_log_written(client):
    from core.models.log import Log

    resp = client.get("/boom")
    assert resp.status_code == 500
    with client.application.app_context():
        logs = Log.query.all()
        assert len(logs) == 1
        log = logs[0]
        data = json.loads(log.message)
        assert data["message"] == "boom"
        assert log.path.endswith("/boom")


def test_502_logged(client):
    from core.models.log import Log

    resp = client.get("/bad")
    assert resp.status_code == 502
    with client.application.app_context():
        logs = Log.query.all()
        assert len(logs) == 1
        log = logs[0]
        data = json.loads(log.message)
        assert data["status"] == 502
        assert log.path.endswith("/bad")


def test_api_request_response_logged(client):
    from core.models.log import Log

    payload = {
        "hello": "world",
        "password": "super-secret",
        "credentials": {
            "access_token": "abc",
            "refresh_token": "xyz",
            "note": "keep",
        },
        "items": [
            {"name": "public"},
            {"refresh_token": "nested"},
        ],
    }
    resp = client.post("/api/ping", json=payload)
    assert resp.status_code == 200
    with client.application.app_context():
        logs = Log.query.order_by(Log.id).all()
        assert len(logs) == 2
        req_log, resp_log = logs
        req_data = json.loads(req_log.message)
        resp_data = json.loads(resp_log.message)
        assert req_log.event == "api.input"
        assert resp_log.event == "api.output"
        assert req_data["method"] == "POST"
        assert req_data["json"]["hello"] == "world"
        assert req_data["json"]["password"] == "***"
        assert req_data["json"]["credentials"]["access_token"] == "***"
        assert req_data["json"]["credentials"]["refresh_token"] == "***"
        assert req_data["json"]["credentials"]["note"] == "keep"
        assert req_data["json"]["items"][0]["name"] == "public"
        assert req_data["json"]["items"][1]["refresh_token"] == "***"
        assert resp_data["status"] == 200
        assert resp_data["json"]["ok"] is True
        assert resp_data["json"]["access_token"] == "***"
        assert resp_data["json"]["echo"]["hello"] == "world"
        assert resp_data["json"]["echo"]["password"] == "***"
        assert resp_data["json"]["echo"]["credentials"]["access_token"] == "***"
        assert resp_data["json"]["echo"]["credentials"]["note"] == "keep"
        assert resp_data["json"]["echo"]["items"][0]["name"] == "public"
        assert resp_data["json"]["echo"]["items"][1]["refresh_token"] == "***"
        assert req_log.request_id == resp_log.request_id
        assert req_log.path.endswith("/api/ping")
        assert resp_log.path.endswith("/api/ping")


def test_api_form_logging_masks_sensitive_data(client):
    from core.models.log import Log

    resp = client.post(
        "/api/form",
        data={
            "username": "alice",
            "password": "top-secret",
            "access_token": "form-access",
        },
    )
    assert resp.status_code == 200

    with client.application.app_context():
        logs = Log.query.order_by(Log.id).all()
        assert len(logs) == 2
        req_log, resp_log = logs
        req_data = json.loads(req_log.message)
        resp_data = json.loads(resp_log.message)

        assert req_log.event == "api.input"
        assert resp_log.event == "api.output"
        assert req_data["form"]["username"] == "alice"
        assert req_data["form"]["password"] == "***"
        assert req_data["form"]["access_token"] == "***"
        assert resp_data["json"]["ok"] is True
        assert resp_data["json"]["refresh_token"] == "***"


def test_unauthorized_logging_records_context(app):
    from core.models.log import Log

    headers = {
        "User-Agent": "pytest-agent",
        "X-Forwarded-For": "203.0.113.5",
    }

    with app.test_request_context(
        "/admin/dashboard?foo=bar",
        headers=headers,
        environ_overrides={"REMOTE_ADDR": "192.0.2.10"},
    ):
        flask_session["_user_id"] = "user-123"
        response = app.login_manager.unauthorized()
        assert response.status_code == 302

    with app.app_context():
        logs = Log.query.order_by(Log.id).all()
        assert len(logs) == 1
        log_entry = logs[0]
        payload = json.loads(log_entry.message)

        assert log_entry.event == "auth.unauthorized"
        assert payload["event"] == "auth.unauthorized"
        assert payload["id"] == log_entry.request_id
        assert payload["timestamp"].endswith("Z")

        expected_hash = hashlib.sha256("user-123".encode("utf-8")).hexdigest()
        assert payload["user"]["id_hash"] == expected_hash
        assert payload["user"]["is_authenticated"] is True

        assert payload["request"]["method"] == "GET"
        assert payload["request"]["path"] == "/admin/dashboard"
        assert payload["request"]["full_path"].startswith("/admin/dashboard?foo=bar")
        assert payload["request"]["ip"] == "203.0.113.5"
        assert payload["request"]["forwarded_for"] == "203.0.113.5"
        assert payload["request"]["user_agent"] == "pytest-agent"
        assert payload["message"] == "Redirected to login due to unauthorized access."


def test_status_change_logged(client):
    """Statusフィールドの変更がログに記録されることを確認する。"""
    import json
    from core.db import db
    from core.utils import log_status_change
    from core.models.log import Log
    from core.models.google_account import GoogleAccount
    from core.models.picker_session import PickerSession

    with client.application.app_context():
        gacc = GoogleAccount(email="a@example.com", scopes="scope")
        db.session.add(gacc)
        db.session.commit()

        ps = PickerSession(account_id=gacc.id)
        db.session.add(ps)
        db.session.commit()

        old = ps.status
        ps.status = "ready"
        log_status_change(ps, old, ps.status)
        db.session.commit()

        log = Log.query.filter_by(event="status.change").order_by(Log.id.desc()).first()
        data = json.loads(log.message)
        assert data["model"] == "PickerSession"
        assert data["to"] == "ready"
