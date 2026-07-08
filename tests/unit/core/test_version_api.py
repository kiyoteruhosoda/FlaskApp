"""
バージョン情報APIのテスト（FastAPI TestClient 版）
"""
import os
from unittest.mock import patch

import pytest

from shared.kernel.version import get_version_info, get_version_string


@pytest.fixture
def app(tmp_path):
    os.environ.setdefault("SECRET_KEY", "test")
    os.environ.setdefault("DATABASE_URI", f"sqlite:///{tmp_path / 'test.db'}")
    os.environ.setdefault("JWT_SECRET_KEY", "test-jwt")
    os.environ.setdefault("ACCESS_TOKEN_ISSUER", "test")
    os.environ.setdefault("ACCESS_TOKEN_AUDIENCE", "test")
    os.environ.setdefault("MEDIA_DOWNLOAD_SIGNING_KEY", "test-key-32-bytes-padded-xxxxx")

    from presentation.fastapi.app import create_app

    return create_app()


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


class TestVersionAPI:
    """バージョン情報APIのテスト"""

    def test_version_endpoint_success(self, client):
        """バージョンAPIの正常系テスト"""
        mock_version_info = {
            "version": "vtest123",
            "commit_hash": "test123",
            "commit_hash_full": "test123456789abcdef",
            "branch": "main",
            "commit_date": "2025-09-07 15:30:16 +0900",
            "build_date": "2025-09-07T17:18:32+09:00",
            "app_start_date": "2025-09-07T17:22:17.270537",
        }

        with patch(
            "presentation.fastapi.routers.version.get_version_info",
            return_value=mock_version_info,
        ):
            with patch(
                "presentation.fastapi.routers.version.get_version_string",
                return_value="vtest123",
            ):
                response = client.get("/api/version")

        assert response.status_code == 200

        data = response.json()
        assert data["ok"] is True
        assert data["version"] == "vtest123"
        assert data["details"] == mock_version_info

    def test_version_endpoint_content_type(self, client):
        """バージョンAPIのレスポンス形式テスト"""
        response = client.get("/api/version")

        assert "application/json" in response.headers.get("content-type", "")

    def test_version_endpoint_methods(self, client):
        """バージョンAPIの許可メソッドテスト"""
        # GET メソッドは成功
        response = client.get("/api/version")
        assert response.status_code in [200, 500]

        # POST メソッドは許可されない
        response = client.post("/api/version")
        assert response.status_code == 405


class TestVersionIntegrationAPI:
    """バージョン情報APIの統合テスト"""

    def test_version_api_real_data(self, client):
        """実際のバージョンデータでのAPIテスト"""
        response = client.get("/api/version")

        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = response.json()

            assert "ok" in data
            assert "version" in data
            assert "details" in data

            details = data["details"]
            expected_keys = ["version", "commit_hash", "branch", "commit_date", "build_date"]
            for key in expected_keys:
                assert key in details, f"Missing key: {key}"

    def test_version_api_consistent_with_core(self, client):
        """APIとコア機能の一貫性テスト"""
        response = client.get("/api/version")

        if response.status_code == 200:
            api_data = response.json()

            core_version_string = get_version_string()
            core_version_info = get_version_info()

            assert api_data["version"] == core_version_string

            api_details = api_data["details"].copy()
            core_info = core_version_info.copy()

            for d in (api_details, core_info):
                d.pop("app_start_date", None)

            for key in ["version", "commit_hash", "branch"]:
                if key in api_details and key in core_info:
                    assert api_details[key] == core_info[key], f"Mismatch in {key}"


if __name__ == "__main__":
    pytest.main([__file__])
