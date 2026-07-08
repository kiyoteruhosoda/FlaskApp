"""FastAPI バージョン・エコーエンドポイントの統合テスト。"""
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
    return TestClient(app, raise_server_exceptions=True)


class TestVersionEndpoint:
    """バージョンエンドポイントのテスト。"""

    def test_version_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/version")
        assert resp.status_code == 200

    def test_version_response_has_version_field(self, client: TestClient) -> None:
        resp = client.get("/api/version")
        data = resp.json()
        assert "version" in data


class TestEchoEndpoint:
    """エコーエンドポイントのテスト（認証必須のため未認証では 401 になる）。"""

    def test_echo_without_token_returns_401(self, client: TestClient) -> None:
        resp = client.get("/api/echo")
        assert resp.status_code == 401

    def test_echo_post_without_token_returns_401(self, client: TestClient) -> None:
        resp = client.post("/api/echo", json={"hello": "world"})
        assert resp.status_code == 401
