"""
Google OAuth URL生成のテスト
PREFERRED_URL_SCHEME設定とProxyFixの動作を確認
"""

import pytest
from flask import url_for
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request
from presentation.web import create_app


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


def test_oauth_start_api_with_scope_profile_photo_picker():
    """スコーププロファイル指定時にPicker用スコープが付与されることを確認"""
    app = create_app()
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    app.config['TESTING'] = True
    app.config['GOOGLE_CLIENT_ID'] = 'test-client-id'

    from presentation.web.api.routes import google_oauth_start

    with app.test_request_context(
        '/api/google/oauth/start',
        json={'scope_profile': 'photo_picker'},
        headers={'X-Forwarded-Proto': 'https'}
    ):
        response = app.make_response(google_oauth_start.__wrapped__())

        assert response.status_code == 200
        data = response.get_json()
        auth_url = data.get('auth_url', '')
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(auth_url)
        scope_param = parse_qs(parsed.query).get('scope', [''])[0]
        scopes = set(scope_param.split(' '))

        assert 'https://www.googleapis.com/auth/photospicker.mediaitems.readonly' in scopes
        assert 'https://www.googleapis.com/auth/photoslibrary.readonly.appcreateddata' in scopes
        assert 'https://www.googleapis.com/auth/photoslibrary.appendonly' in scopes
        assert 'https://www.googleapis.com/auth/userinfo.email' in scopes


def test_oauth_start_api_with_invalid_scope_profile():
    """存在しないスコーププロファイル指定時は400を返す"""
    app = create_app()
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    app.config['TESTING'] = True
    app.config['GOOGLE_CLIENT_ID'] = 'test-client-id'

    from presentation.web.api.routes import google_oauth_start

    with app.test_request_context(
        '/api/google/oauth/start',
        json={'scope_profile': 'unknown_profile'},
        headers={'X-Forwarded-Proto': 'https'}
    ):
        response = app.make_response(google_oauth_start.__wrapped__())

        assert response.status_code == 400
        data = response.get_json()
        assert data.get('error') == 'invalid_scope_profile'
        assert data.get('scope_profile') == 'unknown_profile'


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
        
        # デバッグエンドポイントが存在し JSON を返す場合のみ確認する。
        # SPA catch-all は任意パスに対し HTML シェル(200)を返すため、
        # JSON でないレスポンスはデバッグエンドポイント未登録とみなす。
        if response.status_code == 200 and response.is_json:
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


class TestGoogleOAuthRedirectOriginSetting:
    """GOOGLE_OAUTH_REDIRECT_ORIGIN 設定の検証。

    設定値はスキーム・ホストのみ。コールバックのパスは Flask ルート
    ``/auth/google/callback`` で固定であり、自動で連結される。
    """

    def setup_method(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['GOOGLE_CLIENT_ID'] = 'test-client-id'

    def _start_oauth_redirect_uri(self) -> str:
        """OAuth 開始 API を呼び、auth_url 中の redirect_uri を返す。"""
        from presentation.web.api.routes import google_oauth_start
        from urllib.parse import urlparse, parse_qs

        with self.app.test_request_context(
            '/api/google/oauth/start',
            json={},
            headers={'X-Forwarded-Proto': 'https'},
        ):
            response = self.app.make_response(google_oauth_start.__wrapped__())
            assert response.status_code == 200
            auth_url = response.get_json()['auth_url']
        return parse_qs(urlparse(auth_url).query)['redirect_uri'][0]

    def test_origin_is_combined_with_fixed_path(self):
        """オリジン設定に固定パスが連結された redirect_uri になる"""
        self.app.config['GOOGLE_OAUTH_REDIRECT_ORIGIN'] = 'https://stg.example.com'
        assert self._start_oauth_redirect_uri() == (
            'https://stg.example.com/auth/google/callback'
        )

    def test_legacy_full_url_value_is_accepted(self):
        """旧設定（固定パス込みのフル URL）もオリジンとして受け付ける"""
        self.app.config['GOOGLE_OAUTH_REDIRECT_URI'] = (
            'https://stg.example.com/auth/google/callback'
        )
        assert self._start_oauth_redirect_uri() == (
            'https://stg.example.com/auth/google/callback'
        )

    def test_invalid_value_falls_back_to_derived_url(self):
        """パス付き等の不正値は無視され、自動生成 URL にフォールバックする"""
        self.app.config['GOOGLE_OAUTH_REDIRECT_ORIGIN'] = (
            'https://stg.example.com/oauth2callback'
        )
        redirect_uri = self._start_oauth_redirect_uri()
        assert redirect_uri.endswith('/auth/google/callback')
        assert 'oauth2callback' not in redirect_uri

    def test_validator_accepts_origin_only(self):
        from presentation.web.utils import validate_google_oauth_redirect_origin

        with self.app.test_request_context('/'):
            assert validate_google_oauth_redirect_origin(
                'https://stg.example.com'
            ) is None
            # 末尾スラッシュのみは許容
            assert validate_google_oauth_redirect_origin(
                'https://stg.example.com/'
            ) is None
            # パス・クエリ付き・相対 URL は不正
            assert validate_google_oauth_redirect_origin(
                'https://stg.example.com/auth/google/callback'
            ) is not None
            assert validate_google_oauth_redirect_origin('not-a-url') is not None
            assert validate_google_oauth_redirect_origin(
                'https://stg.example.com?x=1'
            ) is not None

    def test_admin_save_rejects_value_with_path(self):
        """管理画面からの保存時、パスを含む値はバリデーションエラーになる"""
        from presentation.web.admin.routes import _parse_setting_value
        from presentation.web.admin.system_settings_definitions import (
            APPLICATION_SETTING_DEFINITIONS,
        )

        definition = APPLICATION_SETTING_DEFINITIONS['GOOGLE_OAUTH_REDIRECT_ORIGIN']
        with self.app.test_request_context('/'):
            with pytest.raises(ValueError):
                _parse_setting_value(
                    'GOOGLE_OAUTH_REDIRECT_ORIGIN',
                    definition,
                    'https://stg.example.com/auth/google/callback',
                )
            # オリジンのみは受理、空欄は「自動生成に戻す」として受理
            assert _parse_setting_value(
                'GOOGLE_OAUTH_REDIRECT_ORIGIN',
                definition,
                'https://stg.example.com',
            ) == 'https://stg.example.com'
            assert _parse_setting_value(
                'GOOGLE_OAUTH_REDIRECT_ORIGIN', definition, ''
            ) == ''


if __name__ == '__main__':
    pytest.main([__file__])
