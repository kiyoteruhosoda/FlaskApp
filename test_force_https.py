#!/usr/bin/env python3
"""
強制HTTPS設定のテストスクリプト
X-Forwarded-Proto ヘッダーの有無に関係なく、httpsが生成されるかを確認
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
app.config['FORCE_HTTPS'] = os.environ.get('FORCE_HTTPS', 'False').lower() == 'true'

# リバースプロキシ対応
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

def secure_url_for(endpoint, **values):
    """
    強制HTTPS設定が有効な場合、常にhttpsスキームでURLを生成する
    """
    if app.config.get('FORCE_HTTPS', False):
        # 強制HTTPSが有効な場合
        url = url_for(endpoint, _external=True, **values)
        if url.startswith('http://'):
            url = url.replace('http://', 'https://', 1)
        return url
    else:
        # 通常のurl_for（ProxyFixとPREFERRED_URL_SCHEMEに依存）
        return url_for(endpoint, _external=True, **values)

# テスト用のルート
@app.route('/auth/google/callback')
def google_oauth_callback():
    return 'callback'

def test_url_generation():
    print(f"PREFERRED_URL_SCHEME: {app.config['PREFERRED_URL_SCHEME']}")
    print(f"FORCE_HTTPS: {app.config['FORCE_HTTPS']}")
    print()
    
    # テスト1: X-Forwarded-Proto: httpsあり
    print("=== Test 1: With X-Forwarded-Proto: https ===")
    with app.test_request_context('/', headers={'X-Forwarded-Proto': 'https'}):
        callback_url = secure_url_for('google_oauth_callback')
        print(f"Generated callback URL: {callback_url}")
    
    # テスト2: X-Forwarded-Proto: httpあり
    print("\n=== Test 2: With X-Forwarded-Proto: http ===")
    with app.test_request_context('/', headers={'X-Forwarded-Proto': 'http'}):
        callback_url = secure_url_for('google_oauth_callback')
        print(f"Generated callback URL: {callback_url}")
    
    # テスト3: X-Forwarded-Protoヘッダーなし
    print("\n=== Test 3: Without X-Forwarded-Proto header ===")
    with app.test_request_context('/'):
        callback_url = secure_url_for('google_oauth_callback')
        print(f"Generated callback URL: {callback_url}")
    
    # テスト4: 通常のurl_forとの比較
    print("\n=== Test 4: Comparison with regular url_for ===")
    with app.test_request_context('/'):
        regular_url = url_for('google_oauth_callback', _external=True)
        secure_url = secure_url_for('google_oauth_callback')
        print(f"Regular url_for: {regular_url}")
        print(f"secure_url_for: {secure_url}")

if __name__ == '__main__':
    test_url_generation()
