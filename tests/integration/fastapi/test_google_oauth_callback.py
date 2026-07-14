"""Google OAuth コールバック（FastAPI ``/auth/google/callback``）の統合テスト。

Flask から FastAPI への移行時にコールバックルートが実装されず、Google からの
リダイレクトが SPA catch-all に吸われて「TOP 画面に戻るだけで連携されない」
不具合が発生していた（回帰防止）。

React SPA はサーバー側の flash を表示できないため、コールバックは結果を
クエリパラメータ（``google_link=ok|error`` / ``email`` / ``reason``）で戻し先へ
引き渡す。また、コールバック到達時に認証クッキーが失効していてもアカウントを
正しいユーザーへ紐づけられるよう、OAuth 開始時に保存した ``user_id`` を使う。
"""
from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def client(app_context, monkeypatch):
    """app_context のインメモリ DB を共有する FastAPI テストクライアント。"""
    engine = app_context
    # OAuth トークンの保存に暗号鍵が必要（GoogleAccount.oauth_token_json は暗号化）
    monkeypatch.setenv(
        "ENCRYPTION_KEY", "base64:" + base64.urlsafe_b64encode(b"0" * 32).decode()
    )

    from presentation.fastapi.app import create_app
    from shared.kernel.database.session import get_db

    session_factory = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )

    def _override_get_db():
        db = session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app, raise_server_exceptions=True)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _create_user(email: str = "link-user@example.com"):
    from shared.kernel.database.db import db
    from shared.infrastructure.models.user import User

    user = User(email=email)
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    return user


def _save_state(token: str, user_id, *, scopes=None, redirect="/admin/google-accounts"):
    from shared.kernel.oauth_state_store import save_state

    save_state(
        token,
        {
            "state": token,
            "scopes": scopes if scopes is not None else ["scope-a"],
            "redirect": redirect,
            "user_id": user_id,
        },
    )


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


@pytest.mark.integration
def test_callback_links_account_and_redirects_with_ok(client):
    """成功時: saved user_id に紐づけ、戻り先に google_link=ok を付与する。"""
    from shared.infrastructure.models.google_account import GoogleAccount

    user = _create_user()
    _save_state("state-123", user.id, redirect="/profile")

    with patch(
        "shared.infrastructure.http_logging.log_requests_and_send",
        side_effect=_mock_google_responses(),
    ):
        response = client.get(
            "/auth/google/callback?code=abc&state=state-123",
            follow_redirects=False,
        )

    assert response.status_code in (302, 303)
    parts = urlsplit(response.headers["location"])
    assert parts.path == "/profile"
    query = parse_qs(parts.query)
    assert query.get("google_link") == ["ok"]
    assert query.get("email") == ["linked@gmail.com"]

    account = GoogleAccount.query.filter_by(email="linked@gmail.com").first()
    assert account is not None
    assert account.user_id == user.id
    assert account.status == "active"
    assert account.oauth_token_json  # トークンが暗号化保存されている


@pytest.mark.integration
def test_callback_claims_orphan_account(client):
    """未紐付け（user_id=None）の行は、連携時に当該ユーザーへ引き取る。"""
    from shared.kernel.database.db import db
    from shared.infrastructure.models.google_account import GoogleAccount

    user = _create_user("claimer@example.com")
    orphan = GoogleAccount(user_id=None, email="orphan@gmail.com", scopes="", status="active")
    db.session.add(orphan)
    db.session.commit()
    orphan_id = orphan.id

    _save_state("state-123", user.id)

    with patch(
        "shared.infrastructure.http_logging.log_requests_and_send",
        side_effect=_mock_google_responses("orphan@gmail.com"),
    ):
        response = client.get(
            "/auth/google/callback?code=abc&state=state-123",
            follow_redirects=False,
        )

    assert response.status_code in (302, 303)
    # コールバックは別セッションでコミットするため、テスト側の共有セッションの
    # アイデンティティマップを破棄してから DB の最新状態を読み直す。
    db.session.expire_all()
    assert GoogleAccount.query.filter_by(email="orphan@gmail.com").count() == 1
    claimed = db.session.get(GoogleAccount, orphan_id)
    assert claimed.user_id == user.id


@pytest.mark.integration
def test_callback_does_not_steal_other_users_account(client):
    """同じ Google メールを別ユーザーが連携しても既存ユーザーの行を奪わない。"""
    from shared.kernel.database.db import db
    from shared.infrastructure.models.google_account import GoogleAccount

    owner = _create_user("owner@example.com")
    other = _create_user("other@example.com")
    existing = GoogleAccount(
        user_id=owner.id, email="shared@gmail.com", scopes="old-scope", status="active"
    )
    db.session.add(existing)
    db.session.commit()
    owner_account_id = existing.id

    _save_state("state-123", other.id)

    with patch(
        "shared.infrastructure.http_logging.log_requests_and_send",
        side_effect=_mock_google_responses("shared@gmail.com"),
    ):
        response = client.get(
            "/auth/google/callback?code=abc&state=state-123",
            follow_redirects=False,
        )

    assert response.status_code in (302, 303)
    owner_account = db.session.get(GoogleAccount, owner_account_id)
    assert owner_account.user_id == owner.id
    assert owner_account.scopes == "old-scope"
    other_account = GoogleAccount.query.filter_by(
        email="shared@gmail.com", user_id=other.id
    ).first()
    assert other_account is not None
    assert other_account.id != owner_account_id
    assert GoogleAccount.query.filter_by(email="shared@gmail.com").count() == 2


@pytest.mark.integration
def test_callback_invalid_state_redirects_with_error(client):
    """state 不一致: 戻り先に google_link=error / reason=invalid_state を付与する。"""
    from shared.infrastructure.models.google_account import GoogleAccount

    user = _create_user()
    _save_state("expected-state", user.id, redirect="/profile")

    response = client.get(
        "/auth/google/callback?code=abc&state=wrong-state",
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query.get("google_link") == ["error"]
    assert query.get("reason") == ["invalid_state"]
    assert GoogleAccount.query.count() == 0


@pytest.mark.integration
def test_callback_invalid_state_is_logged(client, caplog):
    """state 不一致は診断ログ（warning）を残す。

    ``/auth/google/callback`` は ``/api`` 配下ではなくリクエストログの対象外の
    ため、明示的に記録しないと「エラーが起きたのにログに何も出ない」状態になる
    （回帰防止）。
    """
    user = _create_user()
    _save_state("expected-state", user.id, redirect="/profile")

    with caplog.at_level(
        "WARNING", logger="presentation.fastapi.routers.google_oauth"
    ):
        client.get(
            "/auth/google/callback?code=abc&state=wrong-state",
            follow_redirects=False,
        )

    records = [
        r
        for r in caplog.records
        if getattr(r, "event", None) == "google.oauth.invalid_state"
    ]
    assert records, "invalid_state のときに診断ログが出力されていない"
    assert records[0].levelname == "WARNING"


@pytest.mark.integration
def test_callback_without_user_redirects_with_login_required(client):
    """紐づけ先ユーザーが特定できない state はエラーとして中断する。"""
    from shared.infrastructure.models.google_account import GoogleAccount

    _save_state("state-123", None, redirect="/profile")

    response = client.get(
        "/auth/google/callback?code=abc&state=state-123",
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query.get("google_link") == ["error"]
    assert query.get("reason") == ["login_required"]
    assert GoogleAccount.query.count() == 0


@pytest.mark.integration
def test_callback_without_encryption_key_redirects_with_error(client, monkeypatch):
    """暗号鍵未設定時: 500 にせず reason=encryption_key_missing で戻す。"""
    from shared.infrastructure.models.google_account import GoogleAccount

    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    user = _create_user("nokey@example.com")
    _save_state("state-123", user.id, redirect="/profile")

    with patch(
        "shared.infrastructure.http_logging.log_requests_and_send",
        side_effect=_mock_google_responses(),
    ):
        response = client.get(
            "/auth/google/callback?code=abc&state=state-123",
            follow_redirects=False,
        )

    assert response.status_code in (302, 303)
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query.get("google_link") == ["error"]
    assert query.get("reason") == ["encryption_key_missing"]
    assert GoogleAccount.query.count() == 0
