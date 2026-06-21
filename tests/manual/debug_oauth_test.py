#!/usr/bin/env python3
"""
OAuth URL生成の実際の動作テスト
"""

import requests
import json

from shared.application.api_urls import build_api_url, get_api_base_url

def test_oauth_url_generation():
    """実際のアプリケーションでOAuth URL生成をテスト"""
    base_url = get_api_base_url()

    print("=== OAuth URL生成テスト ===\n")
    print(f"Base URL: {base_url}\n")
    
    # 1. 通常のリクエスト（X-Forwarded-Protoなし）
    print("1. 通常のリクエスト:")
    try:
        response = requests.get(build_api_url("debug/oauth-url"))
        if response.status_code == 200:
            data = response.json()
            print(f"  - Callback URL: {data.get('callback_url')}")
            print(f"  - HTTPS: {data.get('is_https')}")
            print(f"  - Request Scheme: {data.get('request_scheme')}")
            print(f"  - X-Forwarded-Proto: {data.get('x_forwarded_proto')}")
            print(f"  - PREFERRED_URL_SCHEME: {data.get('preferred_url_scheme')}")
        else:
            print(f"  Error: {response.status_code}")
    except Exception as e:
        print(f"  Error: {e}")
    
    print()
    
    # 2. X-Forwarded-Proto: httpsヘッダー付き
    print("2. X-Forwarded-Proto: https ヘッダー付き:")
    try:
        headers = {"X-Forwarded-Proto": "https"}
        response = requests.get(build_api_url("debug/oauth-url"), headers=headers)
        if response.status_code == 200:
            data = response.json()
            print(f"  - Callback URL: {data.get('callback_url')}")
            print(f"  - HTTPS: {data.get('is_https')}")
            print(f"  - Request Scheme: {data.get('request_scheme')}")
            print(f"  - X-Forwarded-Proto: {data.get('x_forwarded_proto')}")
            print(f"  - PREFERRED_URL_SCHEME: {data.get('preferred_url_scheme')}")
        else:
            print(f"  Error: {response.status_code}")
    except Exception as e:
        print(f"  Error: {e}")
    
    print()
    
    # 3. ヘッダー情報の詳細確認
    print("3. 詳細ヘッダー情報:")
    try:
        headers = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "n.nolumia.com"}
        response = requests.get(build_api_url("debug/headers"), headers=headers)
        if response.status_code == 200:
            data = response.json()
            print(f"  - Generated Callback URL: {data.get('generated_callback_url')}")
            print(f"  - Request is secure: {data.get('request_is_secure')}")
            print(f"  - Request scheme: {data.get('request_scheme')}")
            print(f"  - Request host URL: {data.get('request_host_url')}")
            print(f"  - Config PREFERRED_URL_SCHEME: {data.get('config', {}).get('PREFERRED_URL_SCHEME')}")
        else:
            print(f"  Error: {response.status_code}")
    except Exception as e:
        print(f"  Error: {e}")

if __name__ == "__main__":
    test_oauth_url_generation()
