"""Google OAuth コールバックのリンク結果通知とユーザー紐づけを検証する。

React SPA は Flask の flash を表示できないため、コールバックは結果を
クエリパラメータ（google_link=ok|error, email, reason）で戻り先に引き渡す。
また、コールバック時に JWT クッキーが失効していてもアカウントを正しい
ユーザーへ紐づけられるよう、OAuth 開始時に保存した user_id を使う。
"""
from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest

from shared.infrastructure.models.google_account import GoogleAccount
from shared.infrastructure.models.user import User
from presentation.web.bootstrap.extensions import db


@pytest.fixture
def client(app_context):
    # OAuth トークンの保存に暗号鍵が必要（GoogleAccount.oauth_token_json は暗号化される）
    app_context.config["ENCRYPTION_KEY"] = base64.urlsafe_b64encode(b"0" * 32).decode()
    return app_context.test_client()


def _create_user(email: str = "link-user@example.com") -> User:
    user = User(email=email)
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    return user


def _mock_google_responses(email: str = "linked@gmail.com"):
    """トークン交換 → userinfo の2リクエストを模擬する side_effect を返す。"""
    token_res = MagicMock()
    token_res.json.return_value = {
        "access_token": "at",
        "refresh_token": "rt",
        "expires_in": 3600,
    }
    userinfo_res = MagicMock()
    userinfo_res.ok = True
    userinfo_res.json.return_value = {"email": email}
    return [token_res, userinfo_res]


def test_callback_links_account_and_redirects_with_ok(client):
    """成功時: saved user_id に紐づけ、戻り先に google_link=ok を付与する。"""
    user = _create_user()

    with client.session_transaction() as sess:
        sess["google_oauth_state"] = {
            "state": "state-123",
            "scopes": ["scope-a"],
            "redirect": "/profile",
            "user_id": user.id,
        }

    with patch(
        "presentation.web.auth.routes.log_requests_and_send",
        side_effect=_mock_google_responses(),
    ):
        response = client.get(
            "/auth/google/callback?code=abc&state=state-123",
            follow_redirects=False,
        )

    assert response.status_code in (302, 303)
    parts = urlsplit(response.headers["Location"])
    assert parts.path == "/profile"
    query = parse_qs(parts.query)
    assert query.get("google_link") == ["ok"]
    assert query.get("email") == ["linked@gmail.com"]

    account = GoogleAccount.query.filter_by(email="linked@gmail.com").first()
    assert account is not None
    assert account.user_id == user.id
    assert account.status == "active"


def test_callback_invalid_state_redirects_with_error(client):
    """state 不一致: 戻り先に google_link=error / reason=invalid_state を付与する。"""
    with client.session_transaction() as sess:
        sess["google_oauth_state"] = {
            "state": "expected-state",
            "redirect": "/profile",
            "user_id": 1,
        }

    response = client.get(
        "/auth/google/callback?code=abc&state=wrong-state",
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    parts = urlsplit(response.headers["Location"])
    assert parts.path == "/profile"
    query = parse_qs(parts.query)
    assert query.get("google_link") == ["error"]
    assert query.get("reason") == ["invalid_state"]
    assert GoogleAccount.query.count() == 0


def test_callback_without_user_redirects_with_login_required(client):
    """紐づけ先ユーザーが特定できない場合はエラーとして中断する。"""
    with client.session_transaction() as sess:
        sess["google_oauth_state"] = {
            "state": "state-123",
            "redirect": "/profile",
            # user_id なし（旧フローの state）かつ未認証
        }

    response = client.get(
        "/auth/google/callback?code=abc&state=state-123",
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    query = parse_qs(urlsplit(response.headers["Location"]).query)
    assert query.get("google_link") == ["error"]
    assert query.get("reason") == ["login_required"]
    assert GoogleAccount.query.count() == 0


def test_google_accounts_mine_filter_returns_only_own_accounts(client):
    """GET /api/google/accounts?mine=1 は自分に紐づくアカウントのみ返す。"""
    me = _create_user("me@example.com")
    other = _create_user("other@example.com")
    db.session.add_all(
        [
            GoogleAccount(user_id=me.id, email="mine@gmail.com", scopes="s"),
            GoogleAccount(user_id=other.id, email="theirs@gmail.com", scopes="s"),
            GoogleAccount(user_id=None, email="orphan@gmail.com", scopes="s"),
        ]
    )
    db.session.commit()

    login = client.post(
        "/auth/login",
        data={"email": me.email, "password": "password123"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)

    response = client.get("/api/google/accounts?mine=1")
    assert response.status_code == 200
    emails = [item["email"] for item in response.get_json()["items"]]
    assert emails == ["mine@gmail.com"]

    # mine 指定なしは従来どおり全件（管理向け）
    response_all = client.get("/api/google/accounts")
    assert response_all.status_code == 200
    assert len(response_all.get_json()["items"]) == 3
