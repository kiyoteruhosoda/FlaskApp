"""``access_token`` Cookie による認証フォールバックの回帰テスト。

過去に FastAPI の ``get_current_principal`` が Authorization ヘッダーの
Bearer トークンのみを参照しており、Cookie を読まなかった。このため
``<img src="/api/dl/{token}">`` のように Authorization ヘッダーを付与できず
Cookie のみを送るブラウザリクエストが常に ``401 authentication_required``
となり、取り込んだ画像（サムネイル）が表示できなかった。

ログイン時に ``access_token`` Cookie が設定される（auth ルーター）ため、
認証依存はこの Cookie をフォールバックとして利用しなければならない。
本テストは Cookie 経由でトークンを渡した場合に認証が成立することを確認する。
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URI", "sqlite:///:memory:")

from presentation.fastapi.dependencies.auth import (  # noqa: E402
    ACCESS_TOKEN_COOKIE,
    get_current_principal,
)
from shared.application.authenticated_principal import AuthenticatedPrincipal  # noqa: E402
from shared.kernel.database.session import get_db  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    """``get_current_principal`` だけを検証する最小 FastAPI アプリ。

    本番の ``create_app`` はカスタムルーターや SPA catch-all を持ち、認証依存の
    Cookie フォールバック単体を検証するには過剰なため、依存関数を直接組み込む。
    """
    app = FastAPI()

    @app.get("/api/_probe/whoami")
    async def _whoami(
        principal: AuthenticatedPrincipal = Depends(get_current_principal),
    ) -> dict:
        return {"id": principal.id}

    app.dependency_overrides[get_db] = lambda: MagicMock()

    yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        subject_type="individual",
        subject_id=42,
        identifier="user@example.com",
    )


def test_no_credentials_returns_401(client: TestClient) -> None:
    resp = client.get("/api/_probe/whoami")
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "authentication_required"


def test_cookie_token_authenticates(client: TestClient) -> None:
    with patch(
        "presentation.fastapi.services.token_service."
        "TokenService.verify_access_token_with_reason",
        return_value=(_principal(), None),
    ) as verify:
        resp = client.get(
            "/api/_probe/whoami",
            cookies={ACCESS_TOKEN_COOKIE: "cookie-jwt-value"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"id": 42}
    # Cookie の値がそのまま検証に渡されていること
    verify.assert_called_once()
    assert verify.call_args.args[0] == "cookie-jwt-value"


def test_authorization_header_takes_precedence(client: TestClient) -> None:
    with patch(
        "presentation.fastapi.services.token_service."
        "TokenService.verify_access_token_with_reason",
        return_value=(_principal(), None),
    ) as verify:
        resp = client.get(
            "/api/_probe/whoami",
            headers={"Authorization": "Bearer header-jwt-value"},
            cookies={ACCESS_TOKEN_COOKIE: "cookie-jwt-value"},
        )

    assert resp.status_code == 200
    assert verify.call_args.args[0] == "header-jwt-value"
