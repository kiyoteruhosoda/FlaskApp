import re
import uuid
from datetime import datetime, timezone

import pytest
from flask import url_for

from shared.infrastructure.models.service_account import ServiceAccount
from shared.infrastructure.models.user import Permission, Role, User
from presentation.web.services.token_service import TokenService
from shared.kernel.database.db import db


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def _login(client, user):
    response = client.post(
        "/auth/login",
        data={"email": user.email, "password": "password123"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)


def _create_user(email="user@example.com", password="password123"):
    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def _assign_permissions(user: User, *codes: str) -> list[str]:
    role = Role(name=f"role-{uuid.uuid4().hex[:8]}")
    db.session.add(role)

    assigned_codes: list[str] = []
    for code in codes:
        permission = Permission(code=code)
        db.session.add(permission)
        role.permissions.append(permission)
        assigned_codes.append(code)

    user.roles.append(role)
    db.session.add(user)
    db.session.commit()
    return assigned_codes


def _create_service_account(app, scopes=None):
    if scopes is None:
        scopes = set()

    with app.app_context():
        account = ServiceAccount(name=f"svc-{uuid.uuid4().hex[:8]}")
        account.set_scopes(scopes)
        db.session.add(account)
        db.session.commit()
        return account.service_account_id


def _service_account_token(client, account_id, scope=None):
    """サービスアカウント用のステートレス Bearer トークンを発行する。

    サービスアカウントはセッションを持たず、リクエストごとに
    ``Authorization: Bearer <token>`` で認証する。テストでは発行した
    トークンを各リクエストのヘッダーに付与して利用する。
    """

    with client.application.app_context():
        account = db.session.get(ServiceAccount, account_id)
        return TokenService.generate_service_account_access_token(
            account, scope=scope or set()
        )


def _bearer_headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_profile_requires_login(client):
    app = client.application
    original_testing = app.config.get("TESTING")
    original_login_disabled = app.config.get("LOGIN_DISABLED")

    try:
        app.config["TESTING"] = False
        app.testing = False
        app.config["LOGIN_DISABLED"] = False
        response = client.get("/auth/profile")
    finally:
        if original_testing is not None:
            app.config["TESTING"] = original_testing
            app.testing = original_testing
        if original_login_disabled is not None:
            app.config["LOGIN_DISABLED"] = original_login_disabled
        else:
            app.config.pop("LOGIN_DISABLED", None)

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_profile_get_shows_preferences(client):
    """プロフィール情報が API 経由で取得できること。

    言語・タイムゾーンの選択 UI は React SPA がクッキーから描画する。
    サーバ側は ``GET /api/auth/me`` でユーザー情報・権限を供給する。
    新規ユーザーは権限を持たない。
    """
    user = _create_user()
    _login(client, user)

    response = client.get("/api/auth/me")
    assert response.status_code == 200
    data = response.get_json()
    assert data["email"] == user.email
    assert data["permissions"] == []


def test_profile_shows_active_permissions_for_user(client):
    user = _create_user()
    codes = _assign_permissions(
        user,
        f"media:view:{uuid.uuid4().hex[:6]}",
        f"album:edit:{uuid.uuid4().hex[:6]}",
    )
    _login(client, user)

    response = client.get("/api/auth/me")
    assert response.status_code == 200

    permissions = response.get_json()["permissions"]
    for code in codes:
        assert code in permissions


def test_profile_post_updates_cookies_and_preferences(client):
    user = _create_user()
    _login(client, user)

    # 言語・タイムゾーンの設定はサーバがプリファレンス用クッキーを発行する
    # （描画自体は SPA が担当する）。
    response = client.post(
        "/auth/profile",
        data={"language": "en", "timezone": "America/New_York"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    cookies = response.headers.getlist("Set-Cookie")
    assert any("lang=en" in cookie for cookie in cookies)
    assert any("tz=America/New_York" in cookie for cookie in cookies)


def test_service_account_profile_hides_totp_button(client):
    account_id = _create_service_account(client.application)
    token = _service_account_token(client, account_id)

    # サービスアカウントは 2FA を利用できない。2FA ステータス API は
    # 個人ユーザー以外には認証エラー(401)を返す。
    response = client.get("/api/auth/2fa/status", headers=_bearer_headers(token))
    assert response.status_code == 401


def test_service_account_profile_shows_scoped_permissions(client):
    """サービスアカウントの実効権限が発行時スコープに限定されること。

    サービスアカウントの権限はトークンの granted scope で決まる。SPA は
    トークンのスコープを参照するため、ここでは発行トークンを検証して
    プリンシパルの権限がリクエストスコープ(album:view)に限定され、
    アカウントが持つ他スコープ(media:view)が含まれないことを確認する。
    """
    requested_scope = {"album:view"}
    account_id = _create_service_account(
        client.application,
        scopes=requested_scope | {"media:view"},
    )
    token = _service_account_token(client, account_id, scope=requested_scope)

    with client.application.app_context():
        principal, _ = TokenService.verify_access_token_with_reason(token)

    assert principal is not None
    permissions = set(getattr(principal, "permissions", set()) or [])
    assert "album:view" in permissions
    assert "media:view" not in permissions


def test_service_account_cannot_access_totp_setup(client):
    account_id = _create_service_account(client.application)
    token = _service_account_token(client, account_id)

    with client.application.test_request_context(base_url="http://localhost"):
        expected_redirect = url_for("dashboard.dashboard", _external=False)

    response = client.get(
        "/auth/setup_totp",
        headers=_bearer_headers(token),
        follow_redirects=False,
    )
    assert response.status_code == 302
    redirect_target = response.headers["Location"]
    assert redirect_target == expected_redirect

    with client.session_transaction() as sess:
        flashes = sess.get("_flashes", [])
        assert any(
            category == "warning"
            and message == "Two-factor authentication is not available for service accounts."
            for category, message in flashes
        )
        assert "setup_totp_secret" not in sess


def test_totp_setup_with_bearer_token_authenticated_user(client):
    user = _create_user()

    with client.application.app_context():
        token = TokenService.generate_access_token(user)

    # TOTP 設定画面は SPA が描画する。設定開始は SPA が呼び出す
    # ``POST /api/auth/2fa/setup`` がシークレットを返すことで検証する。
    response = client.post(
        "/api/auth/2fa/setup",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["secret"]
    assert data["otpauth_uri"]
    assert data["qr_data_uri"]


def test_localtime_filter_respects_timezone_cookie():
    """タイムゾーン変換ロジックが指定 TZ で正しく整形すること。

    旧 ``localtime`` Jinja フィルタは React SPA 移行で廃止された。クッキー由来の
    TZ 解決と整形は純粋関数 ``resolve_timezone`` + ``format_localtime`` に集約
    されているため、それらを直接検証する。
    """
    from shared.kernel.time.timezone import resolve_timezone
    from presentation.web.templating.jinja_filters import format_localtime

    dt = datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc)
    _, tzinfo = resolve_timezone("America/New_York", "UTC")
    formatted = format_localtime(dt, tzinfo, "%Y-%m-%d %H:%M")

    assert formatted == "2024-01-01 10:00"
