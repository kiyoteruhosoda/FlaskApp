"""UI向けの通常ログインフローを検証するテスト群。"""
from __future__ import annotations

from http.cookies import SimpleCookie
from urllib.parse import urlsplit

import pytest

from core.models.user import User
from webapp.extensions import db


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def _create_user(email: str = "ui-user@example.com", password: str = "password123") -> User:
    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def test_auth_login_sets_session_cookie_and_allows_ui_access(client):
    """/auth/login でのログインがセッションクッキーを発行し、UIアクセスが可能になること。"""
    user = _create_user()

    response = client.post(
        "/auth/login",
        data={"email": user.email, "password": "password123"},
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)

    cookies = response.headers.getlist("Set-Cookie")
    session_cookie_name = client.application.config.get("SESSION_COOKIE_NAME", "session")

    cookie_jar = SimpleCookie()
    for header in cookies:
        cookie_jar.load(header)

    assert session_cookie_name in cookie_jar, "セッションクッキーが発行されていません"
    session_cookie = cookie_jar[session_cookie_name]
    assert session_cookie.value, "セッションクッキーの値が空です"
    assert session_cookie.get("httponly") is True

    with client.session_transaction() as session_state:
        expected_identifier = f"individual:{user.id}"
        assert session_state.get("_user_id") == expected_identifier
        assert session_state.get("_fresh") is True

    profile_response = client.get("/auth/profile")
    assert profile_response.status_code == 200


def test_auth_login_honours_next_parameter_and_persists_session(client):
    """next パラメータが指定された場合に期待通りリダイレクトし、セッションが維持されること。"""
    user = _create_user(email="next-user@example.com")

    response = client.post(
        "/auth/login",
        query_string={"next": "/auth/profile"},
        data={"email": user.email, "password": "password123"},
        follow_redirects=False,
    )

    assert response.status_code in (302, 303)

    location = response.headers.get("Location")
    assert location, "Location ヘッダが返却されていません"
    redirected_path = urlsplit(location).path or location
    assert redirected_path == "/auth/profile"

    with client.session_transaction() as session_state:
        expected_identifier = f"individual:{user.id}"
        assert session_state.get("_user_id") == expected_identifier

    profile_response = client.get("/auth/profile")
    assert profile_response.status_code == 200
