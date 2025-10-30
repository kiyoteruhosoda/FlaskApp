import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from core.db import db
from core.models.passkey import PasskeyCredential
from core.models.user import Permission, Role, User
from shared.application.passkey_service import PasskeyRegistrationError
from webapp.auth.routes import (
    PASSKEY_AUTH_CHALLENGE_KEY,
    PASSKEY_REGISTRATION_CHALLENGE_KEY,
    PASSKEY_REGISTRATION_USER_ID_KEY,
)
from webapp.services.gui_access_cookie import API_LOGIN_SCOPE_SESSION_KEY


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def _create_user(email="user@example.com", password="password123"):
    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def _assign_permission(user: User, code: str) -> None:
    role = Role(name=f"role-{user.id}-{code}")
    permission = Permission(code=code)
    role.permissions.append(permission)
    user.roles.append(role)
    db.session.add_all([permission, role, user])
    db.session.commit()


def test_passkey_registration_options_sets_session(monkeypatch, client):
    user = _create_user()
    _login(client, user)

    options_payload = {"publicKey": {"rpId": "example"}}
    challenge = "challenge-value"

    class StubService:
        def generate_registration_options(self, received_user):
            assert received_user.id == user.id
            return options_payload, challenge

    monkeypatch.setattr("webapp.auth.routes.passkey_service", StubService())

    response = client.post("/auth/passkey/options/register")
    assert response.status_code == 200
    body = response.get_json()
    assert body["publicKey"] == options_payload["publicKey"]
    assert "server_time" in body

    with client.session_transaction() as session:
        assert session[PASSKEY_REGISTRATION_CHALLENGE_KEY] == challenge
        assert session[PASSKEY_REGISTRATION_USER_ID_KEY] == user.id
        assert "passkey_registration_timestamp" in session


def test_passkey_verify_register_success(monkeypatch, client):
    user = _create_user()
    _login(client, user)

    record = SimpleNamespace(
        id=7,
        name="Laptop",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        last_used_at=None,
        transports=["internal"],
        backup_eligible=True,
        backup_state=False,
    )

    class StubService:
        def register_passkey(self, **kwargs):
            assert json.loads(kwargs["payload"].decode("utf-8")) == {
                "id": "cred-id",
                "response": {"transports": ["internal"]},
            }
            assert kwargs["expected_challenge"] == "challenge"
            assert kwargs["name"] == "Laptop"
            return record

    monkeypatch.setattr("webapp.auth.routes.passkey_service", StubService())

    with client.session_transaction() as session:
        session[PASSKEY_REGISTRATION_CHALLENGE_KEY] = "challenge"
        session[PASSKEY_REGISTRATION_USER_ID_KEY] = user.id
        session["passkey_registration_timestamp"] = datetime.now(timezone.utc).isoformat()

    payload = {
        "credential": {"id": "cred-id", "response": {"transports": ["internal"]}},
        "label": "Laptop",
    }

    response = client.post(
        "/auth/passkey/verify/register",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["result"] == "ok"
    assert body["passkey"]["id"] == 7
    assert body["passkey"]["name"] == "Laptop"
    assert body["passkey"]["transports"] == ["internal"]
    assert body["passkey"]["backup_eligible"] is True
    assert body["passkey"]["backup_state"] is False

    with client.session_transaction() as session:
        assert PASSKEY_REGISTRATION_CHALLENGE_KEY not in session
        assert PASSKEY_REGISTRATION_USER_ID_KEY not in session
        assert "passkey_registration_timestamp" not in session


def test_passkey_verify_register_handles_error(monkeypatch, client):
    user = _create_user()
    _login(client, user)

    class StubService:
        def register_passkey(self, **kwargs):
            raise PasskeyRegistrationError("verification_failed")

    monkeypatch.setattr("webapp.auth.routes.passkey_service", StubService())

    with client.session_transaction() as session:
        session[PASSKEY_REGISTRATION_CHALLENGE_KEY] = "challenge"
        session[PASSKEY_REGISTRATION_USER_ID_KEY] = user.id
        session["passkey_registration_timestamp"] = datetime.now(timezone.utc).isoformat()

    response = client.post(
        "/auth/passkey/verify/register",
        data=json.dumps({"credential": {}}),
        content_type="application/json",
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "verification_failed"

    with client.session_transaction() as session:
        assert PASSKEY_REGISTRATION_CHALLENGE_KEY not in session
        assert PASSKEY_REGISTRATION_USER_ID_KEY not in session
        assert "passkey_registration_timestamp" not in session


def test_passkey_login_options_sets_challenge(monkeypatch, client):
    options_payload = {"publicKey": {}}
    challenge = "auth-challenge"

    class StubService:
        def generate_authentication_options(self):
            return options_payload, challenge

    monkeypatch.setattr("webapp.auth.routes.passkey_service", StubService())

    response = client.post("/auth/passkey/options/login")
    assert response.status_code == 200
    body = response.get_json()
    assert body["publicKey"] == options_payload["publicKey"]
    assert "server_time" in body

    with client.session_transaction() as session:
        assert session[PASSKEY_AUTH_CHALLENGE_KEY] == challenge
        assert "passkey_auth_timestamp" in session


def test_passkey_verify_login_success(monkeypatch, client):
    user = _create_user()
    _assign_permission(user, "gui:view")

    class StubService:
        def authenticate(self, **kwargs):
            assert json.loads(kwargs["payload"].decode("utf-8")) == {"id": "cred", "raw": "data"}
            assert kwargs["expected_challenge"] == "auth-challenge"
            return user

    monkeypatch.setattr("webapp.auth.routes.passkey_service", StubService())

    issued_tokens = {"scope": None}

    def fake_generate_token_pair(received_user, scope):
        issued_tokens["scope"] = scope
        return "access-token", "refresh-token"

    monkeypatch.setattr("webapp.auth.routes.TokenService.generate_token_pair", staticmethod(fake_generate_token_pair))

    with client.session_transaction() as session:
        session[PASSKEY_AUTH_CHALLENGE_KEY] = "auth-challenge"
        session["passkey_auth_timestamp"] = datetime.now(timezone.utc).isoformat()

    payload = {
        "credential": {"id": "cred", "raw": "data"},
        "next": "/dashboard",
    }

    response = client.post(
        "/auth/passkey/verify/login",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["result"] == "ok"
    assert body["redirect_url"].endswith("/dashboard")
    assert body["requires_role_selection"] is False
    assert body["access_token"] == "access-token"
    assert body["refresh_token"] == "refresh-token"
    assert issued_tokens["scope"] == ["gui:view"]

    cookies = response.headers.getlist("Set-Cookie")
    assert any(cookie.startswith("access_token=access-token") for cookie in cookies)

    with client.session_transaction() as session:
        assert PASSKEY_AUTH_CHALLENGE_KEY not in session
        assert "passkey_auth_timestamp" not in session
        assert session[API_LOGIN_SCOPE_SESSION_KEY] == ["gui:view"]


def test_passkey_verify_login_rejects_inactive_user(monkeypatch, client):
    user = _create_user()
    user.is_active = False
    db.session.add(user)
    db.session.commit()

    class StubService:
        def authenticate(self, **kwargs):
            return user

    monkeypatch.setattr("webapp.auth.routes.passkey_service", StubService())

    with client.session_transaction() as session:
        session[PASSKEY_AUTH_CHALLENGE_KEY] = "inactive-challenge"
        session["passkey_auth_timestamp"] = datetime.now(timezone.utc).isoformat()

    payload = {"credential": {"id": "cred"}}

    response = client.post(
        "/auth/passkey/verify/login",
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == "account_inactive"

    with client.session_transaction() as session:
        assert PASSKEY_AUTH_CHALLENGE_KEY not in session
        assert "passkey_auth_timestamp" not in session
        assert "_user_id" not in session
        assert API_LOGIN_SCOPE_SESSION_KEY not in session


def test_passkey_verify_login_invalid_payload_clears_session(monkeypatch, client):
    user = _create_user()

    class StubService:
        def authenticate(self, **kwargs):
            return user

    monkeypatch.setattr("webapp.auth.routes.passkey_service", StubService())

    with client.session_transaction() as session:
        session[PASSKEY_AUTH_CHALLENGE_KEY] = "auth-challenge"
        session["passkey_auth_timestamp"] = datetime.now(timezone.utc).isoformat()

    response = client.post(
        "/auth/passkey/verify/login",
        data=json.dumps({"credential": "not-a-dict"}),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_payload"

    with client.session_transaction() as session:
        assert PASSKEY_AUTH_CHALLENGE_KEY not in session
        assert "passkey_auth_timestamp" not in session


def test_delete_passkey_removes_record(client):
    user = _create_user()
    _login(client, user)

    credential = PasskeyCredential(
        user=user,
        credential_id="cred",
        public_key="pub",
        sign_count=0,
    )
    db.session.add(credential)
    db.session.commit()

    response = client.post(f"/auth/passkey/{credential.id}/delete")
    assert response.status_code == 200
    body = response.get_json()
    assert body["result"] == "ok"
    assert "server_time" in body

    assert db.session.get(PasskeyCredential, credential.id) is None


def test_delete_passkey_not_found_returns_404(client):
    user = _create_user()
    _login(client, user)

    response = client.post("/auth/passkey/999/delete")
    assert response.status_code == 404
    body = response.get_json()
    assert body["error"] == "not_found"
    assert "server_time" in body
