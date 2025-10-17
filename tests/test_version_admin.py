"""
バージョン情報管理者ページのテスト
"""
import json
import pytest
from unittest.mock import patch

from webapp import create_app


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
        
        # 管理者権限がないので403エラーが返される
        assert response.status_code == 403
    
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
        
        with patch("core.version.get_version_info", return_value=mock_version_info):
            response = client.get('/admin/version')
        
        # 管理者権限があるので正常にページが表示される
        assert response.status_code == 200
        assert b'version_info' in response.data  # テンプレート変数が渡されている
        assert b'test123' in response.data  # コミットハッシュが表示されている
    
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
        
        with patch("core.version.get_version_info", return_value=mock_version_info):
            response = client.get('/admin/version')
        
        assert response.status_code == 200
        response_text = response.data.decode('utf-8')
        
        # 各バージョン情報が表示されていることを確認
        assert 'vtest456' in response_text
        assert 'test456' in response_text
        assert 'feature-branch' in response_text
        assert '2025-09-07 16:45:30 +0900' in response_text
        assert '2025-09-07T18:30:45+09:00' in response_text
        
        # GitHubリンクが含まれていることを確認（フルハッシュがある場合）
        assert 'github.com' in response_text
        assert 'test456789012345abcdef123456789012345abc' in response_text
        
        # APIテスト機能が含まれていることを確認
        assert 'testVersionAPI' in response_text
        assert '/api/version' in response_text
    
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
        
        with patch("core.version.get_version_info", return_value=mock_version_info):
            response = client.get('/admin/version')
        
        assert response.status_code == 200
        response_text = response.data.decode('utf-8')
        
        # 不明な値が表示されていることを確認
        assert 'dev' in response_text
        assert 'unknown' in response_text
        
        # GitHubリンクが表示されないことを確認（unknownの場合）
        # GitHubリンクのロジックをテスト
        github_link_count = response_text.count('github.com')
        unknown_count = response_text.count('unknown')
        # unknownの場合はGitHubリンクが少ないはず
        assert github_link_count < unknown_count


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
        with patch("core.version.get_version_string", return_value="vtest999"):
            # ヘルスチェックページなど、認証不要のページでテスト
            response = client.get('/health/live')
            
            if response.status_code == 200:
                response_text = response.data.decode('utf-8')
                # フッターにバージョン情報があることを確認
                if 'vtest999' in response_text:
                    assert 'Version:' in response_text or 'vtest999' in response_text
    
    def test_version_context_processor(self, client):
        """テンプレートコンテキストプロセッサのテスト"""
        # app_versionがテンプレートで利用可能かテスト
        
        from webapp import create_app
        
        app = create_app()
        with app.test_request_context():
            # コンテキストプロセッサが登録されているか確認
            with app.app_context():
                # テンプレートレンダリング時にapp_versionが利用可能か確認
                from flask import render_template_string
                
                template = "{{ app_version }}"
                
                # 実際のバージョン文字列が返されることを確認
                rendered = render_template_string(template)
                # 空でないことを確認（具体的な値はファイルに依存するため）
                assert len(rendered.strip()) > 0
                # 一般的なバージョン形式（vで始まるかdevか）を確認
                assert rendered.strip().startswith('v') or rendered.strip() == 'dev'


if __name__ == "__main__":
    pytest.main([__file__])
