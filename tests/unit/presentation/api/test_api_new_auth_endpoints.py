"""新規認証 JSON API — パスキー管理・パスワードリセット の単体テスト。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from core.db import db
from core.models.user import User, Role
from core.models.passkey import PasskeyCredential
from core.models.password_reset_token import PasswordResetToken


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _create_user(email: str | None = None, password: str = "password123") -> User:
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=email)
    user.set_password(password)
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


def _create_passkey(user: User, name: str = "Touch ID") -> PasskeyCredential:
    pk = PasskeyCredential(
        user_id=user.id,
        name=name,
        credential_id=b"cred-" + uuid.uuid4().bytes,
        public_key=b"pubkey",
        sign_count=0,
        aaguid="",
        transports=["internal"],
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(pk)
    db.session.commit()
    return pk


@pytest.fixture
def client(app_context):
    return app_context.test_client()


# ---------------------------------------------------------------------------
# Passkey Management API  (/api/auth/passkeys)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("app_context")
class TestPasskeysManagementApi:
    def test_list_passkeys_unauthenticated(self, client):
        """未ログインでは 403 が返る (get_current_user が None)。"""
        res = client.get("/api/auth/passkeys")
        assert res.status_code == 403

    def test_list_passkeys_empty(self, client, app_context):
        user = _create_user()
        _login(client, user)
        res = client.get("/api/auth/passkeys")
        assert res.status_code == 200
        assert res.get_json()["passkeys"] == []

    def test_list_passkeys_with_credentials(self, client, app_context):
        user = _create_user()
        _create_passkey(user, name="Touch ID")
        _create_passkey(user, name="Security Key")
        _login(client, user)

        res = client.get("/api/auth/passkeys")
        assert res.status_code == 200
        passkeys = res.get_json()["passkeys"]
        assert len(passkeys) == 2
        names = {p["name"] for p in passkeys}
        assert names == {"Touch ID", "Security Key"}

    def test_list_passkeys_only_own(self, client, app_context):
        """他のユーザーのパスキーは返さない。"""
        user1 = _create_user()
        user2 = _create_user()
        _create_passkey(user1, name="User1 Key")
        _create_passkey(user2, name="User2 Key")

        _login(client, user1)
        res = client.get("/api/auth/passkeys")
        assert res.status_code == 200
        passkeys = res.get_json()["passkeys"]
        assert len(passkeys) == 1
        assert passkeys[0]["name"] == "User1 Key"

    def test_delete_passkey(self, client, app_context):
        user = _create_user()
        pk = _create_passkey(user, name="To Delete")
        _login(client, user)

        res = client.delete(f"/api/auth/passkeys/{pk.id}")
        assert res.status_code == 200
        assert res.get_json()["result"] == "deleted"

        list_res = client.get("/api/auth/passkeys")
        assert list_res.get_json()["passkeys"] == []

    def test_delete_passkey_not_found(self, client, app_context):
        user = _create_user()
        _login(client, user)

        res = client.delete("/api/auth/passkeys/9999")
        assert res.status_code == 404

    def test_delete_other_users_passkey(self, client, app_context):
        """他のユーザーのパスキーは削除できない。"""
        user1 = _create_user()
        user2 = _create_user()
        pk = _create_passkey(user2, name="User2 Key")

        _login(client, user1)
        res = client.delete(f"/api/auth/passkeys/{pk.id}")
        assert res.status_code == 404


# ---------------------------------------------------------------------------
# Password Reset JSON API  (/api/auth/password/forgot | /api/auth/password/reset)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("app_context")
class TestPasswordResetJsonApi:
    def test_forgot_password_missing_email(self, client):
        res = client.post("/api/auth/password/forgot", json={})
        assert res.status_code == 400

    def test_forgot_password_mail_disabled(self, client, app_context):
        """メール無効時は 503 を返す。"""
        user = _create_user("reset@example.com")
        # mail is disabled in test env (no SMTP config)
        res = client.post(
            "/api/auth/password/forgot",
            json={"email": user.email},
        )
        assert res.status_code == 503
        assert res.get_json()["error"] == "mail_disabled"

    def test_forgot_password_mail_enabled(self, client, app_context):
        """メール有効時は 200 と sent:true を返す。"""
        user = _create_user("mailer@example.com")
        with patch(
            "presentation.web.services.password_reset_service.PasswordResetService.create_reset_request"
        ) as mock_reset:
            mock_reset.return_value = (True, None)
            res = client.post(
                "/api/auth/password/forgot",
                json={"email": user.email},
            )
        assert res.status_code == 200
        assert res.get_json()["sent"] is True

    def test_forgot_password_unknown_email_returns_200(self, client, app_context):
        """ユーザー列挙防止のため不明アドレスでも 200 を返す。"""
        with patch(
            "presentation.web.services.password_reset_service.PasswordResetService.create_reset_request"
        ) as mock_reset:
            mock_reset.return_value = (True, None)
            res = client.post(
                "/api/auth/password/forgot",
                json={"email": "nobody@example.com"},
            )
        assert res.status_code == 200

    def test_reset_password_invalid_token(self, client):
        res = client.post(
            "/api/auth/password/reset",
            json={"token": "bad-token", "password": "newpassword123"},
        )
        assert res.status_code == 400
        assert res.get_json()["error"] == "invalid_token"

    def test_reset_password_success(self, client, app_context):
        """有効なトークンでパスワードリセットできる。"""
        from presentation.web.services.password_reset_service import PasswordResetService

        user = _create_user("reset-ok@example.com")
        raw_token = PasswordResetService.generate_reset_token()
        token_obj = PasswordResetToken.create_token(user.email, raw_token)
        db.session.add(token_obj)
        db.session.commit()

        res = client.post(
            "/api/auth/password/reset",
            json={"token": raw_token, "password": "brandnewpassword"},
        )
        assert res.status_code == 200
        assert res.get_json()["reset"] is True

        db.session.expire_all()
        updated_user = User.query.filter_by(email=user.email).first()
        assert updated_user.check_password("brandnewpassword")

    def test_reset_password_short_password(self, client, app_context):
        from presentation.web.services.password_reset_service import PasswordResetService

        user = _create_user("reset-short@example.com")
        raw_token = PasswordResetService.generate_reset_token()
        token_obj = PasswordResetToken.create_token(user.email, raw_token)
        db.session.add(token_obj)
        db.session.commit()

        res = client.post(
            "/api/auth/password/reset",
            json={"token": raw_token, "password": "short"},
        )
        assert res.status_code == 400
        assert res.get_json()["error"] == "password_too_short"

    def test_reset_password_missing_fields(self, client):
        res = client.post("/api/auth/password/reset", json={})
        assert res.status_code == 400
