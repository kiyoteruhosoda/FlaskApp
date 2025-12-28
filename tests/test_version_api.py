"""
バージョン情報APIのテスト
"""
import json
import pytest
from unittest.mock import patch

from webapp import create_app
from core.version import get_version_info, get_version_string


class TestVersionAPI:
    """バージョン情報APIのテスト"""
    
    @pytest.fixture
    def client(self):
        """テスト用Flaskクライアント"""
        app = create_app()
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    def test_version_endpoint_success(self, client):
        """バージョンAPIの正常系テスト"""
        mock_version_info = {
            "version": "vtest123",
            "commit_hash": "test123",
            "commit_hash_full": "test123456789abcdef",
            "branch": "main",
            "commit_date": "2025-09-07 15:30:16 +0900",
            "build_date": "2025-09-07T17:18:32+09:00",
            "app_start_date": "2025-09-07T17:22:17.270537"
        }
        
        with patch("webapp.api.version.get_version_info", return_value=mock_version_info):
            with patch("webapp.api.version.get_version_string", return_value="vtest123"):
                response = client.get('/api/version')
        
        assert response.status_code == 200
        
        data = json.loads(response.data)
        assert data["ok"] is True
        assert data["version"] == "vtest123"
        assert data["details"] == mock_version_info
    
    def test_version_endpoint_error(self, client):
        """バージョンAPIのエラー系テスト"""
        with patch("webapp.api.version.get_version_info", side_effect=Exception("Test error")):
            response = client.get('/api/version')
        
        assert response.status_code == 500
        
        data = json.loads(response.data)
        assert data["ok"] is False
        assert data["version"] == "unknown"
        assert "error" in data
    
    def test_version_endpoint_content_type(self, client):
        """バージョンAPIのレスポンス形式テスト"""
        response = client.get('/api/version')
        
        assert response.content_type == 'application/json'
    
    def test_version_endpoint_methods(self, client):
        """バージョンAPIの許可メソッドテスト"""
        # GET メソッドは成功
        response = client.get('/api/version')
        assert response.status_code in [200, 500]  # エラーでも405ではない
        
        # POST メソッドは許可されない
        response = client.post('/api/version')
        assert response.status_code == 405
        
        # PUT メソッドは許可されない
        response = client.put('/api/version')
        assert response.status_code == 405


class TestVersionIntegrationAPI:
    """バージョン情報APIの統合テスト"""
    
    @pytest.fixture
    def client(self):
        """テスト用Flaskクライアント"""
        app = create_app()
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    def test_version_api_real_data(self, client):
        """実際のバージョンデータでのAPIテスト"""
        response = client.get('/api/version')
        
        # レスポンスが正常であることを確認
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = json.loads(response.data)
            
            # 必須フィールドの存在確認
            assert "ok" in data
            assert "version" in data
            assert "details" in data
            
            # detailsの構造確認
            details = data["details"]
            expected_keys = ["version", "commit_hash", "branch", "commit_date", "build_date"]
            for key in expected_keys:
                assert key in details, f"Missing key: {key}"
    
    def test_version_api_consistent_with_core(self, client):
        """APIとコア機能の一貫性テスト"""
        # APIからバージョン情報を取得
        response = client.get('/api/version')
        
        if response.status_code == 200:
            api_data = json.loads(response.data)
            
            # コア機能から直接取得
            core_version_string = get_version_string()
            core_version_info = get_version_info()
            
            # 一貫性の確認
            assert api_data["version"] == core_version_string
            
            # app_start_dateは動的に変わるので除外して比較
            api_details = api_data["details"].copy()
            core_info = core_version_info.copy()
            
            if "app_start_date" in api_details:
                del api_details["app_start_date"]
            if "app_start_date" in core_info:
                del core_info["app_start_date"]
            
            # 基本的な情報の一貫性確認
            for key in ["version", "commit_hash", "branch"]:
                if key in api_details and key in core_info:
                    assert api_details[key] == core_info[key], f"Mismatch in {key}"


if __name__ == "__main__":
    pytest.main([__file__])
