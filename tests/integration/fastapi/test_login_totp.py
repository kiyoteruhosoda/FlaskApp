"""ログイン TOTP フローの統合テスト。

POST /api/auth/login エンドポイントにおける TOTP 認証シナリオを検証する:
- TOTP 未設定ユーザー: メール＋パスワードのみでログイン成功
- TOTP 設定済みユーザー: TOTP トークン未送信 → 401 (totp_required)
- TOTP 設定済みユーザー: 不正な TOTP トークン → 401 (invalid_totp)
- TOTP 設定済みユーザー: 正しい TOTP トークン → 200
"""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pyotp
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URI", "sqlite:///:memory:")

from presentation.fastapi.app import create_app  # noqa: E402


def _make_user_model(totp_secret: str | None = None) -> MagicMock:
    """モックユーザーモデルを生成する。"""
    user = MagicMock()
    user.totp_secret = totp_secret
    user.roles = []
    user.all_permissions = set()
    user.must_change_password = False
    return user


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


_AUTH_SERVICE_AUTHENTICATE = (
    "shared.application.auth_service.AuthService.authenticate_with_reason"
)
_TOKEN_SERVICE_GENERATE = (
    "presentation.fastapi.services.token_service.TokenService.generate_token_pair"
)


class TestLoginWithoutTOTP:
    """TOTP 未設定ユーザーのログインテスト。"""

    def test_login_without_totp_returns_200(self, client: TestClient) -> None:
        user = _make_user_model(totp_secret=None)
        with (
            patch(_AUTH_SERVICE_AUTHENTICATE, return_value=(user, None)),
            patch(_TOKEN_SERVICE_GENERATE, return_value=("access_tok", "refresh_tok")),
        ):
            resp = client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": "password"},
            )
        assert resp.status_code == 200

    def test_login_without_totp_response_has_access_token(self, client: TestClient) -> None:
        user = _make_user_model(totp_secret=None)
        with (
            patch(_AUTH_SERVICE_AUTHENTICATE, return_value=(user, None)),
            patch(_TOKEN_SERVICE_GENERATE, return_value=("access_tok", "refresh_tok")),
        ):
            resp = client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": "password"},
            )
        data = resp.json()
        assert data["access_token"] == "access_tok"
        assert data["refresh_token"] == "refresh_tok"

    def test_login_with_invalid_credentials_returns_401(self, client: TestClient) -> None:
        with patch(_AUTH_SERVICE_AUTHENTICATE, return_value=(None, "invalid_password")):
            resp = client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": "wrong"},
            )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "invalid_credentials"


class TestLoginWithTOTP:
    """TOTP 設定済みユーザーのログインテスト。"""

    def test_login_without_totp_token_returns_401_totp_required(self, client: TestClient) -> None:
        secret = pyotp.random_base32()
        user = _make_user_model(totp_secret=secret)
        with patch(_AUTH_SERVICE_AUTHENTICATE, return_value=(user, None)):
            resp = client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": "password"},
            )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "totp_required"

    def test_login_with_invalid_totp_token_returns_401_invalid_totp(self, client: TestClient) -> None:
        secret = pyotp.random_base32()
        user = _make_user_model(totp_secret=secret)
        with patch(_AUTH_SERVICE_AUTHENTICATE, return_value=(user, None)):
            resp = client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": "password", "token": "000000"},
            )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error"] == "invalid_totp"

    def test_login_with_valid_totp_token_returns_200(self, client: TestClient) -> None:
        secret = pyotp.random_base32()
        valid_token = pyotp.TOTP(secret).now()
        user = _make_user_model(totp_secret=secret)
        with (
            patch(_AUTH_SERVICE_AUTHENTICATE, return_value=(user, None)),
            patch(_TOKEN_SERVICE_GENERATE, return_value=("access_tok", "refresh_tok")),
        ):
            resp = client.post(
                "/api/auth/login",
                json={
                    "email": "user@example.com",
                    "password": "password",
                    "token": valid_token,
                },
            )
        assert resp.status_code == 200

    def test_login_with_valid_totp_token_response_has_access_token(self, client: TestClient) -> None:
        secret = pyotp.random_base32()
        valid_token = pyotp.TOTP(secret).now()
        user = _make_user_model(totp_secret=secret)
        with (
            patch(_AUTH_SERVICE_AUTHENTICATE, return_value=(user, None)),
            patch(_TOKEN_SERVICE_GENERATE, return_value=("access_tok_totp", "refresh_tok_totp")),
        ):
            resp = client.post(
                "/api/auth/login",
                json={
                    "email": "user@example.com",
                    "password": "password",
                    "token": valid_token,
                },
            )
        data = resp.json()
        assert data["access_token"] == "access_tok_totp"

    def test_login_totp_not_sent_when_totp_is_none_does_not_raise(self, client: TestClient) -> None:
        """token フィールドが None のとき TOTP 未設定なら成功することを確認する。"""
        user = _make_user_model(totp_secret=None)
        with (
            patch(_AUTH_SERVICE_AUTHENTICATE, return_value=(user, None)),
            patch(_TOKEN_SERVICE_GENERATE, return_value=("tok_a", "tok_b")),
        ):
            resp = client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": "password", "token": None},
            )
        assert resp.status_code == 200


_SETTINGS_REQUIRE_PW_CHANGE = (
    "shared.kernel.settings.settings.ApplicationSettings.require_password_change_on_first_login"
)


class TestLoginMustChangePassword:
    """must_change_password フラグと requires_password_change レスポンスのテスト。"""

    def test_requires_password_change_false_when_flag_and_setting_both_false(
        self, client: TestClient
    ) -> None:
        """must_change_password=False かつ設定 OFF → requires_password_change=False。"""
        user = _make_user_model(totp_secret=None)
        user.must_change_password = False
        with (
            patch(_AUTH_SERVICE_AUTHENTICATE, return_value=(user, None)),
            patch(_TOKEN_SERVICE_GENERATE, return_value=("tok_a", "tok_b")),
            patch(_SETTINGS_REQUIRE_PW_CHANGE, new_callable=lambda: property(lambda self: False)),
        ):
            resp = client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": "password"},
            )
        assert resp.status_code == 200
        assert resp.json()["requires_password_change"] is False

    def test_requires_password_change_true_when_flag_true_and_setting_enabled(
        self, client: TestClient
    ) -> None:
        """must_change_password=True かつ設定 ON → requires_password_change=True。"""
        user = _make_user_model(totp_secret=None)
        user.must_change_password = True
        with (
            patch(_AUTH_SERVICE_AUTHENTICATE, return_value=(user, None)),
            patch(_TOKEN_SERVICE_GENERATE, return_value=("tok_a", "tok_b")),
            patch(_SETTINGS_REQUIRE_PW_CHANGE, new_callable=lambda: property(lambda self: True)),
        ):
            resp = client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": "password"},
            )
        assert resp.status_code == 200
        assert resp.json()["requires_password_change"] is True

    def test_requires_password_change_false_when_flag_true_but_setting_disabled(
        self, client: TestClient
    ) -> None:
        """must_change_password=True でも設定 OFF なら requires_password_change=False。"""
        user = _make_user_model(totp_secret=None)
        user.must_change_password = True
        with (
            patch(_AUTH_SERVICE_AUTHENTICATE, return_value=(user, None)),
            patch(_TOKEN_SERVICE_GENERATE, return_value=("tok_a", "tok_b")),
            patch(_SETTINGS_REQUIRE_PW_CHANGE, new_callable=lambda: property(lambda self: False)),
        ):
            resp = client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": "password"},
            )
        assert resp.status_code == 200
        assert resp.json()["requires_password_change"] is False

    def test_requires_password_change_false_when_flag_false_and_setting_enabled(
        self, client: TestClient
    ) -> None:
        """must_change_password=False なら設定 ON でも requires_password_change=False。"""
        user = _make_user_model(totp_secret=None)
        user.must_change_password = False
        with (
            patch(_AUTH_SERVICE_AUTHENTICATE, return_value=(user, None)),
            patch(_TOKEN_SERVICE_GENERATE, return_value=("tok_a", "tok_b")),
            patch(_SETTINGS_REQUIRE_PW_CHANGE, new_callable=lambda: property(lambda self: True)),
        ):
            resp = client.post(
                "/api/auth/login",
                json={"email": "user@example.com", "password": "password"},
            )
        assert resp.status_code == 200
        assert resp.json()["requires_password_change"] is False
