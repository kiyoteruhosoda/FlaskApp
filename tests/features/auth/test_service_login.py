import uuid

import pytest

from core.models.service_account import ServiceAccount
from webapp.extensions import db
from webapp.services.token_service import TokenService


@pytest.fixture
def app(app_context):
    return app_context


@pytest.fixture
def client(app):
    return app.test_client()


def test_service_login_respects_authorized_scope(app, client):
    with app.app_context():
        account = ServiceAccount(name=f"svc-{uuid.uuid4().hex[:8]}")
        account.set_scopes({"totp:view", "totp:write"})
        db.session.add(account)
        db.session.commit()

        limited_token = TokenService.generate_service_account_access_token(
            account,
            scope={"totp:view"},
        )

    response = client.get(
        "/auth/servicelogin",
        headers={"Authorization": f"Bearer {limited_token}"},
        follow_redirects=False,
    )

    assert response.status_code == 302

    list_response = client.get("/api/totp")
    assert list_response.status_code == 200

    create_response = client.post(
        "/api/totp",
        json={"secret": "JBSWY3DPEHPK3PXP"},
    )
    assert create_response.status_code == 403
    assert create_response.get_json()["error"] == "forbidden"
