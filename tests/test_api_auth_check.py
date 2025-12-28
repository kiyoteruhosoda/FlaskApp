import pytest

from webapp.services.token_service import TokenService
from webapp.extensions import db
from core.models.user import User


@pytest.fixture
def client(app_context):
    return app_context.test_client()


@pytest.fixture
def user(app_context):
    account = User(email="jwt-user@example.com")
    account.set_password("secret")
    db.session.add(account)
    db.session.commit()
    return account


def test_auth_check_requires_token(client):
    response = client.get("/api/auth/check")
    assert response.status_code == 401
    payload = response.get_json()
    assert payload["error"] == "authentication_required"


def test_auth_check_accepts_bearer_token(client, user):
    access_token = TokenService.generate_access_token(user)

    response = client.get(
        "/api/auth/check",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == user.id
    assert data["email"] == user.email
    assert data["active"] is True


def test_auth_check_accepts_cookie_token(client, user):
    access_token = TokenService.generate_access_token(user)

    client.set_cookie("access_token", access_token)

    response = client.get("/api/auth/check")

    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == user.id
    assert data["email"] == user.email
    assert data["active"] is True
