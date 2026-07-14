"""認証済みエンドポイントが principal 属性を正しく参照することの回帰テスト。

過去に FastAPI ルーターが存在しない ``principal.user_id`` を参照しており、
``/api/auth/2fa/status`` や ``/api/auth/passkeys`` などの認証済みエンドポイントが
``AttributeError: 'AuthenticatedPrincipal' object has no attribute 'user_id'``
で 500 を返していた。``AuthenticatedPrincipal`` が公開するのは ``id``（= subject_id）
であり ``user_id`` ではない。本テストは実際の ``AuthenticatedPrincipal`` を注入して
これらのエンドポイントが例外なく応答することを確認する。
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URI", "sqlite:///:memory:")

from presentation.fastapi.app import create_app  # noqa: E402
from presentation.fastapi.dependencies.auth import get_current_principal  # noqa: E402
from shared.application.authenticated_principal import AuthenticatedPrincipal  # noqa: E402
from shared.kernel.database.session import get_db  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    app = create_app()

    principal = AuthenticatedPrincipal(
        subject_type="individual",
        subject_id=42,
        identifier="user@example.com",
    )

    user = MagicMock()
    user.id = 42
    user.totp_secret = None

    db = MagicMock()
    db.get.return_value = user
    # /passkeys は db.query(...).filter_by(...).order_by(...).all() を呼ぶ
    db.query.return_value.filter_by.return_value.order_by.return_value.all.return_value = []

    app.dependency_overrides[get_current_principal] = lambda: principal
    app.dependency_overrides[get_db] = lambda: db

    yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


def test_2fa_status_uses_principal_id(client: TestClient) -> None:
    resp = client.get("/api/auth/2fa/status")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False}


def test_passkeys_list_uses_principal_id(client: TestClient) -> None:
    resp = client.get("/api/auth/passkeys")
    assert resp.status_code == 200
    assert resp.json() == {"passkeys": []}
