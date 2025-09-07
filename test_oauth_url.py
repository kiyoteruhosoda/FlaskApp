#!/usr/bin/env python3
"""
Google OAuth URLの生成をテストするスクリプト
PREFERRED_URL_SCHEME設定が正しく反映されるかを確認
"""

import os
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import Flask, url_for
from dotenv import load_dotenv

# .env読み込み
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-key'
app.config['PREFERRED_URL_SCHEME'] = os.environ.get('PREFERRED_URL_SCHEME', 'http')

# リバースプロキシ対応
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# テスト用のルート
@app.route('/auth/google/callback')
def google_oauth_callback():
    return 'callback'

# X-Forwarded-Proto: httpsを模擬するテスト
def test_url_generation():
    with app.test_request_context('/', headers={'X-Forwarded-Proto': 'https'}):
        callback_url = url_for('google_oauth_callback', _external=True)
        print(f"Generated callback URL: {callback_url}")
        print(f"PREFERRED_URL_SCHEME: {app.config['PREFERRED_URL_SCHEME']}")
        
        # OAuth開始時と同様の条件
        from urllib.parse import urlencode
        params = {
            "client_id": "your-client-id",
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": "email",
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": "test-state",
        }
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
        print(f"Full OAuth URL: {auth_url}")

if __name__ == '__main__':
    test_url_generation()
