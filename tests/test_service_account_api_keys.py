import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from flask import jsonify, g

from core.db import db
from core.models.service_account_api_key import ServiceAccountApiKeyLog
from core.models.user import Permission, Role, User
from webapp.auth.api_key_auth import require_api_key_scopes
from webapp.services.service_account_api_key_service import (
    ServiceAccountApiKeyService,
    ServiceAccountApiKeyValidationError,
)
from webapp.services.service_account_service import ServiceAccountService


def _create_service_account(scopes: str) -> int:
    normalized = [scope.strip() for scope in scopes.replace(",", " ").split(" ") if scope.strip()]
    account = ServiceAccountService.create_account(
        name="media-bot",
        description="Media automation",
        jwt_endpoint="https://example.com/jwks/media",
        scope_names=",".join(normalized),
        active=True,
        allowed_scopes=normalized,
    )
    return account.service_account_id


def _login(client, user: User) -> None:
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def _create_user_with_permissions(*permission_codes: str) -> User:
    role = Role(name=f"role-{uuid4().hex}")
    db.session.add(role)

    for code in permission_codes:
        permission = Permission(code=code)
        db.session.add(permission)
        role.permissions.append(permission)

    user = User(email=f"user-{uuid4().hex}@example.com")
    user.set_password("secret")
    user.roles.append(role)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.mark.usefixtures("app_context")
def test_api_key_creation_and_listing(app_context):
    account_id = _create_service_account("media:read media:upload")

    record, api_key_value = ServiceAccountApiKeyService.create_key(
        account_id,
        scopes="media:read",
        expires_at=None,
        created_by="admin@example.com",
    )

    assert api_key_value.startswith("sa-")
    assert record.public_id in api_key_value

    keys = ServiceAccountApiKeyService.list_keys(account_id)
    assert len(keys) == 1
    assert keys[0].scopes == ["media:read"]


@pytest.mark.usefixtures("app_context")
def test_api_key_scope_validation(app_context):
    account_id = _create_service_account("media:read")

    with pytest.raises(ServiceAccountApiKeyValidationError):
        ServiceAccountApiKeyService.create_key(
            account_id,
            scopes="media:write",
            expires_at=None,
            created_by="admin@example.com",
        )


@pytest.mark.usefixtures("app_context")
def test_api_key_expiration_validation(app_context):
    account_id = _create_service_account("media:read")
    past = datetime.now(timezone.utc) - timedelta(days=1)

    with pytest.raises(ServiceAccountApiKeyValidationError):
        ServiceAccountApiKeyService.create_key(
            account_id,
            scopes="media:read",
            expires_at=past,
            created_by="admin@example.com",
        )


@pytest.mark.usefixtures("app_context")
def test_api_key_authentication_and_logging(app_context):
    account_id = _create_service_account("maintenance:read")
    record, api_key_value = ServiceAccountApiKeyService.create_key(
        account_id,
        scopes="maintenance:read",
        expires_at=None,
        created_by="admin@example.com",
    )

    app = app_context

    @app.route("/api/test/protected")
    @require_api_key_scopes(["maintenance:read"])
    def protected_endpoint():
        return jsonify({"service_account": g.service_account.name})

    client = app.test_client()

    response = client.get(
        "/api/test/protected",
        headers={"Authorization": f"ApiKey {api_key_value}"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["service_account"] == "media-bot"

    logs = ServiceAccountApiKeyLog.query.all()
    assert len(logs) == 1
    assert logs[0].api_key_id == record.api_key_id
    assert logs[0].endpoint == "/api/test/protected"

    ServiceAccountApiKeyService.revoke_key(
        account_id, record.api_key_id, actor="admin@example.com"
    )

    response = client.get(
        "/api/test/protected",
        headers={"Authorization": f"ApiKey {api_key_value}"},
    )
    assert response.status_code == 401
    assert response.get_json()["error"] == "Revoked"

    logs = ServiceAccountApiKeyLog.query.all()
    assert len(logs) == 1


@pytest.mark.usefixtures("app_context")
def test_service_account_api_requires_dedicated_permission(app_context):
    account_id = _create_service_account("maintenance:read")
    client = app_context.test_client()
    user = _create_user_with_permissions("service_account:manage")
    _login(client, user)

    response = client.get(f"/api/service_accounts/{account_id}/keys")
    assert response.status_code == 403


@pytest.mark.usefixtures("app_context")
def test_service_account_api_allows_with_dedicated_permission(app_context):
    account_id = _create_service_account("maintenance:read")
    client = app_context.test_client()
    user = _create_user_with_permissions("service_account_api:manage")
    _login(client, user)

    response = client.get(f"/api/service_accounts/{account_id}/keys")
    assert response.status_code == 200
    data = response.get_json()
    assert data["items"] == []
