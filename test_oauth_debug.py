#!/usr/bin/env python3
"""
現在のFlaskアプリケーションでOAuth URLの生成をテストする
"""

import sys
import os
sys.path.insert(0, '/home/kyon/myproject')

from webapp import create_app
from flask import url_for

def test_oauth_url_generation():
    app = create_app()
    
    print(f"PREFERRED_URL_SCHEME config: {app.config.get('PREFERRED_URL_SCHEME')}")
    
    # テスト1: 通常のリクエストコンテキスト
    with app.test_request_context('/'):
        callback_url = url_for('auth.google_oauth_callback', _external=True)
        print(f"Normal context: {callback_url}")
    
    # テスト2: X-Forwarded-Proto: httpsヘッダー付き
    with app.test_request_context('/', headers={'X-Forwarded-Proto': 'https'}):
        callback_url = url_for('auth.google_oauth_callback', _external=True)
        print(f"With X-Forwarded-Proto=https: {callback_url}")
    
    # テスト3: X-Forwarded-Proto: httpsとホスト指定
    with app.test_request_context('/', 
                                  headers={
                                      'X-Forwarded-Proto': 'https',
                                      'Host': 'n.nolumia.com'
                                  }):
        callback_url = url_for('auth.google_oauth_callback', _external=True)
        print(f"With X-Forwarded-Proto=https and Host: {callback_url}")

if __name__ == '__main__':
    test_oauth_url_generation()
