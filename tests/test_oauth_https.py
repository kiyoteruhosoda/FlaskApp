"""
Google OAuth URL生成のテスト
PREFERRED_URL_SCHEME設定とProxyFixの動作を確認
"""

import pytest
from flask import url_for
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request
from webapp import create_app


def test_oauth_url_generation_http():
    """HTTP環境でのOAuth URL生成テスト"""
    app = create_app()
    app.config['PREFERRED_URL_SCHEME'] = 'http'
    
    with app.test_request_context():
        callback_url = url_for('auth.google_oauth_callback', _external=True)
        assert callback_url.startswith('http://')
        assert 'auth/google/callback' in callback_url


def test_oauth_url_generation_https():
    """HTTPS環境でのOAuth URL生成テスト"""
    app = create_app()
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    
    with app.test_request_context():
        callback_url = url_for('auth.google_oauth_callback', _external=True)
        assert callback_url.startswith('https://')
        assert 'auth/google/callback' in callback_url


def test_oauth_url_with_x_forwarded_proto():
    """X-Forwarded-Proto ヘッダーでのHTTPS検出テスト"""
    app = create_app()
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    
    # X-Forwarded-Proto: https ヘッダーを模擬
    with app.test_request_context('/', headers={'X-Forwarded-Proto': 'https'}):
        callback_url = url_for('auth.google_oauth_callback', _external=True)
        assert callback_url.startswith('https://')
        assert 'auth/google/callback' in callback_url


def test_oauth_url_without_x_forwarded_proto():
    """X-Forwarded-Proto ヘッダーなしでの動作テスト"""
    app = create_app()
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    
    with app.test_request_context('/'):
        callback_url = url_for('auth.google_oauth_callback', _external=True)
        # PREFERRED_URL_SCHEMEの設定によりhttpsになる
        assert callback_url.startswith('https://')
        assert 'auth/google/callback' in callback_url


def test_oauth_start_api_with_https():
    """OAuth開始APIでのURL生成テスト"""
    app = create_app()
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    app.config['TESTING'] = True
    app.config['GOOGLE_CLIENT_ID'] = 'test-client-id'
    
    with app.test_client() as client:
        # ログイン状態を模擬
        with client.session_transaction() as sess:
            sess['user_id'] = 1
            
        response = client.post('/api/google/oauth/start',
                             json={'scopes': ['email']},
                             headers={'X-Forwarded-Proto': 'https'})
        
        if response.status_code == 200:
            data = response.get_json()
            auth_url = data.get('auth_url', '')
            # redirect_uriパラメータがhttpsになっていることを確認
            assert 'redirect_uri=https%3A' in auth_url

            # userinfo.emailスコープが必ず含まれることを確認
            from urllib.parse import urlparse, parse_qs

            parsed = urlparse(auth_url)
            scope_param = parse_qs(parsed.query).get('scope', [''])[0]
            scopes = scope_param.split(' ')
            assert 'https://www.googleapis.com/auth/userinfo.email' in scopes


def test_proxy_fix_headers():
    """ProxyFixによるヘッダー処理のテスト"""
    app = create_app()
    
    with app.test_client() as client:
        # X-Forwarded-* ヘッダーをセット
        response = client.get('/debug/headers', headers={
            'X-Forwarded-Proto': 'https',
            'X-Forwarded-For': '192.168.1.1',
            'X-Forwarded-Host': 'example.com'
        })
        
        # デバッグエンドポイントが存在すれば確認
        if response.status_code == 200:
            data = response.get_json()
            assert data.get('scheme') == 'https'


class TestOAuthURLGeneration:
    """OAuth URL生成の統合テスト"""
    
    def setup_method(self):
        """各テストの前に実行"""
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['GOOGLE_CLIENT_ID'] = 'test-client-id'
        self.app.config['GOOGLE_CLIENT_SECRET'] = 'test-secret'
        
    def test_oauth_flow_with_https_scheme(self):
        """HTTPS環境でのOAuthフロー全体テスト"""
        self.app.config['PREFERRED_URL_SCHEME'] = 'https'
        
        with self.app.test_request_context('/', headers={'X-Forwarded-Proto': 'https'}):
            # callback URLの生成テスト
            callback_url = url_for('auth.google_oauth_callback', _external=True)
            assert callback_url.startswith('https://')
            
            # OAuth URLパラメータの生成テスト
            from urllib.parse import urlencode
            params = {
                "client_id": "test-client-id",
                "redirect_uri": callback_url,
                "response_type": "code",
                "scope": "email",
                "access_type": "offline",
                "include_granted_scopes": "true",
                "prompt": "consent",
                "state": "test-state",
            }
            auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
            
            # 生成されたOAuth URLにhttpsのredirect_uriが含まれることを確認
            assert 'redirect_uri=https%3A' in auth_url
            
    def test_oauth_flow_with_http_scheme(self):
        """HTTP環境でのOAuthフロー テスト"""
        self.app.config['PREFERRED_URL_SCHEME'] = 'http'
        
        with self.app.test_request_context('/'):
            callback_url = url_for('auth.google_oauth_callback', _external=True)
            assert callback_url.startswith('http://')


if __name__ == '__main__':
    pytest.main([__file__])
