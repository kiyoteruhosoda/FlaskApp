import base64
from typer.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import httpx

from fpv.cli import app
from core.db import db
from core.models.google_account import GoogleAccount


def _base_env(tmp_path):
    key = base64.urlsafe_b64encode(b"0" * 32).decode("utf-8")
    return {
        "FPV_DB_URL": "sqlite:///:memory:",
        "FPV_NAS_ORIG_DIR": str(tmp_path / "orig"),
        "FPV_NAS_PLAY_DIR": str(tmp_path / "play"),
        "FPV_NAS_THUMBS_DIR": str(tmp_path / "thumbs"),
        "FPV_TMP_DIR": str(tmp_path / "tmp"),
        "FPV_GOOGLE_CLIENT_ID": "client",
        "FPV_GOOGLE_CLIENT_SECRET": "secret",
        "FPV_OAUTH_KEY": f"base64:{key}",
    }


def _setup_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    db.Model.metadata.create_all(engine)
    with Session(engine) as session:
        acc = GoogleAccount(email="a@b", scopes="", status="active", oauth_token_json="{}")
        session.add(acc)
        session.commit()
    return engine


def test_google_tokeninfo(monkeypatch, tmp_path):
    env = _base_env(tmp_path)
    engine = _setup_engine()
    monkeypatch.setattr("fpv.cli.get_engine_from_env", lambda: engine)
    monkeypatch.setattr("fpv.google.refresh_access_token", lambda *a, **k: ("tok", {}))
    monkeypatch.setattr("fpv.google.tokeninfo", lambda t: {"scope": "x y"})
    runner = CliRunner()
    result = runner.invoke(app, ["google", "tokeninfo", "--account-id", "1"], env=env)
    assert result.exit_code == 0
    assert "\"scope\": \"x y\"" in result.stdout


def test_google_diagnose_list(monkeypatch, tmp_path):
    env = _base_env(tmp_path)
    engine = _setup_engine()
    monkeypatch.setattr("fpv.cli.get_engine_from_env", lambda: engine)
    monkeypatch.setattr("fpv.google.refresh_access_token", lambda *a, **k: ("tok", {}))

    def _raise(*a, **k):
        req = httpx.Request("GET", "https://photoslibrary.googleapis.com/v1/mediaItems")
        res = httpx.Response(403, json={"error": {"code": 403, "status": "PERMISSION_DENIED"}})
        raise httpx.HTTPStatusError("boom", request=req, response=res)

    monkeypatch.setattr("fpv.google.list_media_items_once", _raise)
    runner = CliRunner()
    result = runner.invoke(app, ["google", "diagnose-list", "--account-id", "1"], env=env)
    assert result.exit_code != 0
    assert "PERMISSION_DENIED" in result.stdout
