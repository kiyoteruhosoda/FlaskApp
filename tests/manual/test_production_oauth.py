#!/usr/bin/env python3
"""
本番環境での問題を再現するテスト
n.nolumia.com の環境を模擬
"""

import os
import sys
sys.path.insert(0, '/home/kyon/myproject')

from webapp import create_app
from flask import url_for
import logging

def test_production_like_environment():
    """本番環境類似の設定でテスト"""
    
    # 本番環境の設定を模擬
    os.environ['PREFERRED_URL_SCHEME'] = 'https'
    
    app = create_app()
    app.config['SERVER_NAME'] = 'n.nolumia.com'
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    
    print("=== 本番環境模擬テスト ===")
    print(f"SERVER_NAME: {app.config.get('SERVER_NAME')}")
    print(f"PREFERRED_URL_SCHEME: {app.config.get('PREFERRED_URL_SCHEME')}")
    print()
    
    # 1. X-Forwarded-Protoなしの場合
    print("1. X-Forwarded-Proto なし:")
    with app.test_request_context('/', base_url='http://n.nolumia.com'):
        try:
            callback_url = url_for('auth.google_oauth_callback', _external=True)
            print(f"  Callback URL: {callback_url}")
            print(f"  HTTPS: {callback_url.startswith('https://')}")
        except Exception as e:
            print(f"  Error: {e}")
    
    print()
    
    # 2. X-Forwarded-Proto: httpsありの場合
    print("2. X-Forwarded-Proto: https あり:")
    with app.test_request_context('/', 
                                  base_url='http://n.nolumia.com',
                                  headers={'X-Forwarded-Proto': 'https'}):
        try:
            callback_url = url_for('auth.google_oauth_callback', _external=True)
            print(f"  Callback URL: {callback_url}")
            print(f"  HTTPS: {callback_url.startswith('https://')}")
        except Exception as e:
            print(f"  Error: {e}")
    
    print()
    
    # 3. 直接HTTPSでリクエストした場合を模擬
    print("3. HTTPS リクエスト模擬:")
    with app.test_request_context('/', 
                                  base_url='https://n.nolumia.com'):
        try:
            callback_url = url_for('auth.google_oauth_callback', _external=True)
            print(f"  Callback URL: {callback_url}")
            print(f"  HTTPS: {callback_url.startswith('https://')}")
        except Exception as e:
            print(f"  Error: {e}")

def test_with_proxy_fix():
    """ProxyFixの動作を詳細確認"""
    print("\n=== ProxyFix 動作確認 ===")
    
    app = create_app()
    app.config['PREFERRED_URL_SCHEME'] = 'https'
    
    # WSGIアプリケーションを直接テスト
    from werkzeug.test import Client
    from werkzeug.wrappers import Response
    
    client = Client(app.wsgi_app, Response)
    
    # X-Forwarded-Proto ヘッダー付きでリクエスト
    response = client.get('/debug/oauth-url', headers={
        'X-Forwarded-Proto': 'https',
        'X-Forwarded-Host': 'n.nolumia.com'
    })
    
    if response.status_code == 200:
        import json
        data = json.loads(response.get_data(as_text=True))
        print(f"Callback URL: {data.get('callback_url')}")
        print(f"HTTPS: {data.get('is_https')}")
        print(f"Request Scheme: {data.get('request_scheme')}")
        print(f"X-Forwarded-Proto: {data.get('x_forwarded_proto')}")
    else:
        print(f"Error: {response.status_code}")
        print(response.get_data(as_text=True))

if __name__ == "__main__":
    test_production_like_environment()
    test_with_proxy_fix()
