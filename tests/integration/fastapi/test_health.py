"""FastAPI ヘルスチェックエンドポイントの統合テスト。

Strangler Fig 構成（asgi.py）の FastAPI アプリを TestClient で検証する。
DBやRedisへの接続は不要（ヘルスエンドポイントはDB非依存）。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from presentation.fastapi.app import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    """FastAPI TestClient を返す。"""
    app = create_app()
    return TestClient(app, raise_server_exceptions=True)


class TestHealthEndpoints:
    """ヘルスチェックエンドポイントのテスト。"""

    def test_healthz_returns_200(self, client: TestClient) -> None:
        resp = client.get("/healthz")
        assert resp.status_code == 200

    def test_health_live_returns_200(self, client: TestClient) -> None:
        resp = client.get("/health/live")
        assert resp.status_code == 200

    def test_health_ready_returns_200_or_503(self, client: TestClient) -> None:
        # DB/Redis 未接続環境では 503 になることを許容する
        resp = client.get("/health/ready")
        assert resp.status_code in (200, 503)

    def test_healthz_response_has_status_field(self, client: TestClient) -> None:
        resp = client.get("/healthz")
        data = resp.json()
        assert "status" in data

    def test_health_live_response_has_status_field(self, client: TestClient) -> None:
        resp = client.get("/health/live")
        data = resp.json()
        assert "status" in data
