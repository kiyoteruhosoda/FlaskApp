import pytest

from core.models.user import User
from webapp.extensions import db
from webapp.services.token_service import TokenService


@pytest.fixture
def client(app_context):
    return app_context.test_client()


def _create_user(email: str = "logout-user@example.com", password: str = "secret") -> User:
    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def _login_via_session(client, user: User, picker_session_id: str = "picker_sessions/test") -> None:
    with client.session_transaction() as flask_session:
        flask_session["_user_id"] = str(user.id)
        flask_session["_fresh"] = True
        flask_session["picker_session_id"] = picker_session_id


def test_api_logout_revokes_tokens_and_clears_session(client):
    user = _create_user()
    _login_via_session(client, user)

    access_token, refresh_token = TokenService.generate_token_pair(user)
    assert access_token
    assert refresh_token
    assert user.refresh_token_hash is not None
    assert user.check_refresh_token(refresh_token)

    response = client.post("/api/logout")
    assert response.status_code == 200
    assert response.get_json() == {"result": "ok"}

    # Flask-Loginのセッション情報がクリアされていることを確認
    with client.session_transaction() as flask_session:
        assert "_user_id" not in flask_session
        assert "picker_session_id" not in flask_session

    # リフレッシュトークンのハッシュが削除されていることを確認
    db.session.refresh(user)
    assert user.refresh_token_hash is None
    assert not user.check_refresh_token(refresh_token)

    # クッキー削除の指示が返されることを確認
    cookies = response.headers.getlist("Set-Cookie")
    assert any("access_token=;" in cookie for cookie in cookies)
