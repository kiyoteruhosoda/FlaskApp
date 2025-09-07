"""
OAuth URL生成のデバッグ用Blueprint
実際のリクエストでどのようなURLが生成されるかを確認
"""

from flask import Blueprint, request, jsonify, url_for, current_app
import os

debug_bp = Blueprint('debug', __name__)


@debug_bp.route('/headers')
def debug_headers():
    """リクエストヘッダーと環境情報を表示"""
    headers = dict(request.headers)
    environ_info = {
        'HTTP_X_FORWARDED_PROTO': request.environ.get('HTTP_X_FORWARDED_PROTO'),
        'HTTP_X_FORWARDED_FOR': request.environ.get('HTTP_X_FORWARDED_FOR'),
        'HTTP_X_FORWARDED_HOST': request.environ.get('HTTP_X_FORWARDED_HOST'),
        'REQUEST_SCHEME': request.environ.get('REQUEST_SCHEME'),
        'wsgi.url_scheme': request.environ.get('wsgi.url_scheme'),
        'SERVER_NAME': request.environ.get('SERVER_NAME'),
        'SERVER_PORT': request.environ.get('SERVER_PORT'),
    }
    
    # FlaskのURL生成テスト
    try:
        callback_url = url_for('auth.google_oauth_callback', _external=True)
    except Exception as e:
        callback_url = f"Error: {str(e)}"
    
    config_info = {
        'PREFERRED_URL_SCHEME': current_app.config.get('PREFERRED_URL_SCHEME'),
        'SERVER_NAME': current_app.config.get('SERVER_NAME'),
        'APPLICATION_ROOT': current_app.config.get('APPLICATION_ROOT'),
    }
    
    return jsonify({
        'headers': headers,
        'environ': environ_info,
        'config': config_info,
        'generated_callback_url': callback_url,
        'request_is_secure': request.is_secure,
        'request_scheme': request.scheme,
        'request_url': request.url,
        'request_base_url': request.base_url,
        'request_host_url': request.host_url,
    })


@debug_bp.route('/oauth-url')
def debug_oauth_url():
    """OAuth URL生成のテスト"""
    try:
        # コールバックURL生成
        callback_url = url_for('auth.google_oauth_callback', _external=True)
        
        # OAuth URLパラメータ作成
        from urllib.parse import urlencode
        params = {
            "client_id": current_app.config.get('GOOGLE_CLIENT_ID', 'test-client-id'),
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": "email",
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": "debug-state",
        }
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
        
        return jsonify({
            'success': True,
            'callback_url': callback_url,
            'full_oauth_url': auth_url,
            'is_https': callback_url.startswith('https://'),
            'request_scheme': request.scheme,
            'x_forwarded_proto': request.headers.get('X-Forwarded-Proto'),
            'preferred_url_scheme': current_app.config.get('PREFERRED_URL_SCHEME'),
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'request_scheme': request.scheme,
            'x_forwarded_proto': request.headers.get('X-Forwarded-Proto'),
        })


@debug_bp.route('/test-proxy-fix')
def test_proxy_fix():
    """ProxyFixの動作テスト"""
    return jsonify({
        'original_environ_scheme': request.environ.get('wsgi.url_scheme'),
        'request_scheme': request.scheme,
        'request_is_secure': request.is_secure,
        'x_forwarded_proto': request.headers.get('X-Forwarded-Proto'),
        'x_forwarded_for': request.headers.get('X-Forwarded-For'),
        'x_forwarded_host': request.headers.get('X-Forwarded-Host'),
        'server_name': request.environ.get('SERVER_NAME'),
        'server_port': request.environ.get('SERVER_PORT'),
        'http_host': request.environ.get('HTTP_HOST'),
    })
