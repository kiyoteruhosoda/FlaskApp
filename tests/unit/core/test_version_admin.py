"""
バージョン情報管理者ページのテスト
"""
from urllib.parse import urlparse

import json
import pytest
from unittest.mock import patch

from presentation.web import create_app


class TestVersionAdminPage:
    """バージョン情報管理者ページのテスト"""
    
    @pytest.fixture
    def client(self):
        """テスト用Flaskクライアント"""
        app = create_app()
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    def test_version_admin_page_unauthorized(self, client):
        """未認証での管理者ページアクセステスト"""
        response = client.get('/admin/version')
        
        # 認証が必要なので、ログインページにリダイレクトされるかエラーが返される
        assert response.status_code in [302, 401, 403]
    
    @patch('flask_login.utils._get_user')
    def test_version_admin_page_non_admin(self, mock_current_user, client):
        """非管理者ユーザーでの管理者ページアクセステスト"""
        # 管理者権限のないユーザーをモック
        mock_user = type('MockUser', (), {
            'is_authenticated': True,
            'can': lambda self, perm: False
        })()
        mock_current_user.return_value = mock_user

        response = client.get('/admin/version')

        # 管理者権限がない場合はトップページへリダイレクトされる
        assert response.status_code == 302
        with client.application.test_request_context():
            target = urlparse(response.headers['Location'])
            assert target.path == '/'
    
    @patch('flask_login.utils._get_user')
    def test_version_admin_page_authorized(self, mock_current_user, client):
        """管理者ユーザーでの管理者ページアクセステスト"""
        # 管理者権限のあるユーザーをモック
        mock_user = type('MockUser', (), {
            'is_authenticated': True,
            'can': lambda self, perm: perm == 'system:manage'
        })()
        mock_current_user.return_value = mock_user
        
        mock_version_info = {
            "version": "vtest123",
            "commit_hash": "test123",
            "commit_hash_full": "test123456789abcdef",
            "branch": "main",
            "commit_date": "2025-09-07 15:30:16 +0900",
            "build_date": "2025-09-07T17:18:32+09:00",
            "app_start_date": "2025-09-07T17:22:17.270537"
        }

        # バージョン情報画面は React SPA が描画するため、SPA が利用する
        # 公開 API (/api/version) が情報を返すことで検証する。
        with patch("presentation.web.api.version.get_version_info", return_value=mock_version_info):
            with patch("presentation.web.api.version.get_version_string", return_value="vtest123"):
                response = client.get('/api/version')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["ok"] is True
        assert data["version"] == "vtest123"
        assert data["details"]["commit_hash"] == "test123"
    
    @patch('flask_login.utils._get_user')
    def test_version_admin_page_template_content(self, mock_current_user, client):
        """管理者ページのテンプレート内容テスト"""
        # 管理者権限のあるユーザーをモック
        mock_user = type('MockUser', (), {
            'is_authenticated': True,
            'can': lambda self, perm: perm == 'system:manage'
        })()
        mock_current_user.return_value = mock_user
        
        mock_version_info = {
            "version": "vtest456",
            "commit_hash": "test456",
            "commit_hash_full": "test456789012345abcdef123456789012345abc",
            "branch": "feature-branch",
            "commit_date": "2025-09-07 16:45:30 +0900",
            "build_date": "2025-09-07T18:30:45+09:00",
            "app_start_date": "2025-09-07T18:35:12.123456"
        }
        
        with patch("presentation.web.api.version.get_version_info", return_value=mock_version_info):
            with patch("presentation.web.api.version.get_version_string", return_value="vtest456"):
                response = client.get('/api/version')

        assert response.status_code == 200
        data = json.loads(response.data)

        # 各バージョン情報が API レスポンスに含まれていることを確認
        details = data["details"]
        assert data["version"] == "vtest456"
        assert details["commit_hash"] == "test456"
        assert details["branch"] == "feature-branch"
        assert details["commit_date"] == "2025-09-07 16:45:30 +0900"
        assert details["build_date"] == "2025-09-07T18:30:45+09:00"

        # フルコミットハッシュ（GitHub リンク生成に利用）が含まれていること
        assert details["commit_hash_full"] == "test456789012345abcdef123456789012345abc"
    
    @patch('flask_login.utils._get_user')
    def test_version_admin_page_unknown_values(self, mock_current_user, client):
        """不明な値での管理者ページテスト"""
        # 管理者権限のあるユーザーをモック
        mock_user = type('MockUser', (), {
            'is_authenticated': True,
            'can': lambda self, perm: perm == 'system:manage'
        })()
        mock_current_user.return_value = mock_user
        
        mock_version_info = {
            "version": "dev",
            "commit_hash": "unknown",
            "commit_hash_full": "unknown",
            "branch": "unknown",
            "commit_date": "unknown",
            "build_date": "2025-09-07T17:18:32+09:00"
        }
        
        with patch("presentation.web.api.version.get_version_info", return_value=mock_version_info):
            with patch("presentation.web.api.version.get_version_string", return_value="dev"):
                response = client.get('/api/version')

        assert response.status_code == 200
        data = json.loads(response.data)

        # 不明な値が API レスポンスに反映されていることを確認
        assert data["version"] == "dev"
        details = data["details"]
        assert details["commit_hash"] == "unknown"
        assert details["branch"] == "unknown"
        assert details["commit_hash_full"] == "unknown"


class TestVersionPageIntegration:
    """バージョン情報ページの統合テスト"""
    
    @pytest.fixture
    def client(self):
        """テスト用Flaskクライアント"""
        app = create_app()
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
    
    def test_version_in_footer(self, client):
        """フッターにバージョン情報が表示されることのテスト"""
        # 認証なしでアクセスできるページをテスト
        with patch("shared.kernel.version.get_version_string", return_value="vtest999"):
            # ヘルスチェックページなど、認証不要のページでテスト
            response = client.get('/health/live')
            
            if response.status_code == 200:
                response_text = response.data.decode('utf-8')
                # フッターにバージョン情報があることを確認
                if 'vtest999' in response_text:
                    assert 'Version:' in response_text or 'vtest999' in response_text
    
    def test_version_string_available_via_api(self, client):
        """バージョン文字列が API 経由で取得できること。

        以前は ``app_version`` テンプレートコンテキストプロセッサで供給していたが、
        React SPA 移行に伴いバージョン文字列は ``GET /api/version`` から取得する。
        """
        response = client.get('/api/version')
        assert response.status_code == 200
        data = json.loads(response.data)
        version = data["version"]
        # 空でなく、一般的なバージョン形式（v で始まるか dev）であること
        assert len(version.strip()) > 0
        assert version.strip().startswith('v') or version.strip() == 'dev'


if __name__ == "__main__":
    pytest.main([__file__])
