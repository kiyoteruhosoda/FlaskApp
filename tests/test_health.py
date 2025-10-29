"""
Health endpoint tests
"""
import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from flask import current_app

from webapp.extensions import db


class TestHealthEndpoints:
    """Health endpoint tests"""

    def test_health_live_success(self, app_context, client):
        """Test /health/live endpoint returns 200 OK"""
        response = client.get("/health/live")
        assert response.status_code == 200
        
        data = response.get_json()
        assert data["status"] == "ok"

    def test_health_live_no_auth_required(self, app_context, client):
        """Test /health/live endpoint doesn't require authentication"""
        # healthエンドポイントは認証なしでアクセスできることを確認
        response = client.get("/health/live")
        assert response.status_code == 200
        # 認証エラー（401, 403）ではないことを確認
        assert response.status_code not in [401, 403]

    def test_health_ready_basic(self, app_context, client):
        """Test /health/ready basic functionality"""
        response = client.get("/health/ready")
        
        # ステータスコードは200または503のいずれか
        assert response.status_code in [200, 503]
        
        data = response.get_json()
        # 必須フィールドの存在確認
        assert "status" in data
        assert "db" in data
        
        # statusは"ok"または"error"
        assert data["status"] in ["ok", "error"]
        # dbは"ok"または"error"  
        assert data["db"] in ["ok", "error"]

    def test_health_ready_db_error(self, app_context, client):
        """Test /health/ready when database is unavailable"""
        with patch('webapp.extensions.db.session.execute') as mock_execute:
            mock_execute.side_effect = Exception("Database connection failed")
            
            response = client.get("/health/ready")
            assert response.status_code == 503
            
            data = response.get_json()
            assert data["status"] == "error"
            assert data["db"] == "error"

    def test_health_ready_redis_error(self, app_context, client):
        """Test /health/ready when Redis is unavailable"""
        current_app.config['REDIS_URL'] = 'redis://localhost:6379/0'
        
        with patch('redis.from_url') as mock_redis:
            mock_redis.side_effect = Exception("Redis connection failed")
            
            response = client.get("/health/ready")
            assert response.status_code == 503
            
            data = response.get_json()
            assert data["status"] == "error"
            assert data["redis"] == "error"

    def test_health_ready_nas_paths_missing(self, app_context, client):
        """Test /health/ready when NAS paths are missing"""
        # 存在しないパスを設定
        current_app.config['MEDIA_THUMBNAILS_DIRECTORY'] = '/non/existent/path'
        current_app.config['MEDIA_PLAYBACK_DIRECTORY'] = '/another/non/existent/path'
        
        response = client.get("/health/ready")
        assert response.status_code == 503
        
        data = response.get_json()
        assert data["status"] == "error"
        assert data["media_nas_thumbnails_directory"] == "missing"
        assert data["media_nas_playback_directory"] == "missing"

    def test_health_ready_nas_paths_ok(self, app_context, client, tmp_path):
        """Test /health/ready when NAS paths exist"""
        # 一時ディレクトリを使用
        thumbs_dir = tmp_path / "thumbs"
        play_dir = tmp_path / "play"
        thumbs_dir.mkdir()
        play_dir.mkdir()
        
        current_app.config['MEDIA_THUMBNAILS_DIRECTORY'] = str(thumbs_dir)
        current_app.config['MEDIA_PLAYBACK_DIRECTORY'] = str(play_dir)
        
        response = client.get("/health/ready")
        assert response.status_code == 200
        
        data = response.get_json()
        assert data["media_nas_thumbnails_directory"] == "ok"
        assert data["media_nas_playback_directory"] == "ok"

    def test_health_ready_no_redis_config(self, app_context, client):
        """Test /health/ready when Redis is not configured"""
        # Redis設定を削除
        current_app.config.pop('REDIS_URL', None)
        
        response = client.get("/health/ready")
        # Redisが設定されていない場合はチェックしない
        assert response.status_code in [200, 503]  # 他の要因で503になる可能性もある
        
        data = response.get_json()
        # Redisの項目が含まれていないことを確認
        assert "redis" not in data or data.get("redis") is None

    def test_health_beat_no_last_beat(self, app_context, client):
        """Test /health/beat when no last beat is recorded"""
        current_app.config.pop('LAST_BEAT_AT', None)
        
        response = client.get("/health/beat")
        assert response.status_code == 200
        
        data = response.get_json()
        assert data["lastBeatAt"] is None
        assert "server_time" in data
        # ISO8601形式のタイムスタンプであることを確認
        server_time = data["server_time"]
        assert server_time.endswith("Z")
        # パースできることを確認
        datetime.fromisoformat(server_time.replace("Z", "+00:00"))

    def test_health_beat_with_last_beat(self, app_context, client):
        """Test /health/beat when last beat is recorded"""
        test_time = datetime.now(timezone.utc)
        current_app.config['LAST_BEAT_AT'] = test_time
        
        response = client.get("/health/beat")
        assert response.status_code == 200
        
        data = response.get_json()
        assert data["lastBeatAt"] is not None
        assert data["lastBeatAt"] == test_time.isoformat()
        assert "server_time" in data

    def test_health_beat_invalid_last_beat(self, app_context, client):
        """Test /health/beat when last beat is not a datetime object"""
        current_app.config['LAST_BEAT_AT'] = "invalid_datetime_string"
        
        response = client.get("/health/beat")
        assert response.status_code == 200
        
        data = response.get_json()
        assert data["lastBeatAt"] is None
        assert "server_time" in data

    def test_health_endpoints_json_response(self, app_context, client):
        """Test that all health endpoints return JSON"""
        endpoints = ["/health/live", "/health/ready", "/health/beat"]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.content_type == "application/json"
            # JSONがパースできることを確認
            data = response.get_json()
            assert isinstance(data, dict)

    def test_health_endpoints_cors(self, app_context, client):
        """Test CORS headers for health endpoints (if needed)"""
        response = client.get("/health/live")
        # 必要に応じてCORSヘッダーをチェック
        # assert "Access-Control-Allow-Origin" in response.headers


class TestHealthIntegration:
    """Integration tests for health endpoints"""

    def test_health_ready_realistic_scenario(self, app_context, client):
        """Test /health/ready in a realistic scenario"""
        # 実際のアプリケーション設定に近い状態でテスト
        response = client.get("/health/ready")
        
        # レスポンスが有効であることを確認
        assert response.status_code in [200, 503]
        data = response.get_json()
        assert "status" in data
        assert "db" in data
        
        # DBチェックは常に実行される
        assert data["db"] in ["ok", "error"]

    def test_health_endpoints_performance(self, app_context, client):
        """Test that health endpoints respond quickly"""
        import time
        
        endpoints = ["/health/live", "/health/ready", "/health/beat"]
        
        for endpoint in endpoints:
            start_time = time.time()
            response = client.get(endpoint)
            end_time = time.time()
            
            # レスポンス時間が1秒以内であることを確認
            response_time = end_time - start_time
            assert response_time < 1.0, f"{endpoint} took {response_time:.2f} seconds"
            
            # 有効なレスポンスであることを確認
            assert response.status_code in [200, 503]


@pytest.fixture
def client(app_context):
    """Create test client"""
    return app_context.test_client()
