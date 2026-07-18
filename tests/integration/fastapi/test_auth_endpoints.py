"""FastAPI 認証エンドポイント（認証なし部分）の統合テスト。

未認証での保護エンドポイントへのアクセスが 401 を返すことを検証する。
"""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

# テスト用に SQLite インメモリ DB を設定（get_db 依存の解決のため）
os.environ.setdefault("DATABASE_URI", "sqlite:///:memory:")

from presentation.fastapi.app import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


class TestAuthEndpointsUnauthenticated:
    """未認証アクセス時のレスポンスをテスト。"""

    def test_me_without_token_returns_401(self, client: TestClient) -> None:
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_auth_check_without_token_returns_401(self, client: TestClient) -> None:
        resp = client.get("/api/auth/check")
        assert resp.status_code == 401

    def test_roles_without_token_returns_401(self, client: TestClient) -> None:
        resp = client.get("/api/auth/roles")
        assert resp.status_code == 401

    def test_media_list_without_token_returns_401(self, client: TestClient) -> None:
        resp = client.get("/api/media")
        assert resp.status_code == 401

    def test_albums_list_without_token_returns_401(self, client: TestClient) -> None:
        resp = client.get("/api/albums")
        assert resp.status_code == 401

    def test_tags_list_without_token_returns_401(self, client: TestClient) -> None:
        resp = client.get("/api/tags")
        assert resp.status_code == 401


class TestOpenAPISpec:
    """OpenAPI スキーマが生成されることを検証。"""

    def test_openapi_json_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/openapi.json")
        assert resp.status_code == 200

    def test_openapi_json_has_paths(self, client: TestClient) -> None:
        resp = client.get("/api/openapi.json")
        data = resp.json()
        assert "paths" in data
        assert len(data["paths"]) > 0
