import base64
import json

import pytest

from core.crypto import encrypt


@pytest.fixture
def app(tmp_path, monkeypatch):
    db_uri = f"sqlite:///{tmp_path/'test.db'}"
    monkeypatch.setenv("SECRET_KEY", "test")
    monkeypatch.setenv("DATABASE_URI", db_uri)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "sec")
    key = base64.urlsafe_b64encode(b"0" * 32).decode()
    monkeypatch.setenv("OAUTH_TOKEN_KEY", key)
    from webapp.config import Config
    Config.SQLALCHEMY_ENGINE_OPTIONS = {}
    from webapp import create_app
    app = create_app()
    app.config.update(TESTING=True)
    from webapp.extensions import db
    from core.models.user import User
    from core.models.google_account import GoogleAccount
    with app.app_context():
        db.create_all()
        u = User(email="u@example.com")
        u.set_password("pass")
        db.session.add(u)
        acc = GoogleAccount(email="g@example.com", scopes="", oauth_token_json=encrypt(json.dumps({"refresh_token": "r"})))
        db.session.add(acc)
        db.session.commit()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_picker_route(monkeypatch, client, app):
    from core.models.user import User
    with app.app_context():
        user = User.query.first()
        client.post("/auth/login", data={"email": user.email, "password": "pass"}, follow_redirects=True)

    class FakeResp:
        def __init__(self, data):
            self._data = data
            self.status_code = 200
        def json(self):
            return self._data
        def raise_for_status(self):
            pass

    def fake_post(url, *a, **k):
        if url == "https://oauth2.googleapis.com/token":
            return FakeResp({"access_token": "acc"})
        if url == "https://photospicker.googleapis.com/v1/sessions":
            return FakeResp({"pickerUri": "https://picker.example"})
        raise AssertionError("unexpected url" + url)

    monkeypatch.setattr("requests.post", fake_post)
    res = client.get("/picker/1")
    assert b"https://picker.example" in res.data


def test_template_includes_picker_scope():
    path = 'webapp/auth/templates/auth/google_accounts.html'
    with open(path) as f:
        text = f.read()
    assert 'https://www.googleapis.com/auth/photospicker.mediaitems.readonly' in text
