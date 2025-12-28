#!/usr/bin/env python3
"""
Manual health endpoint testing script
健康チェックエンドポイントの手動テスト用スクリプト
"""
import json
import sys
import time
import urllib.request
import urllib.error
from urllib.parse import urljoin

from shared.application.api_urls import get_api_base_url, build_api_url


def test_endpoint(base_url, endpoint, expected_status=200):
    """Test a single health endpoint"""
    url = urljoin(base_url, endpoint)
    print(f"Testing {url}...")
    
    try:
        start_time = time.time()
        with urllib.request.urlopen(url) as response:
            end_time = time.time()
            response_time = (end_time - start_time) * 1000  # ms
            
            status_code = response.getcode()
            content_type = response.headers.get('Content-Type', '')
            body = response.read().decode('utf-8')
            
            print(f"  ✓ Status: {status_code} (expected: {expected_status})")
            print(f"  ✓ Response time: {response_time:.2f}ms")
            print(f"  ✓ Content-Type: {content_type}")
            
            if 'application/json' in content_type:
                try:
                    data = json.loads(body)
                    print(f"  ✓ JSON response: {json.dumps(data, indent=2)}")
                except json.JSONDecodeError as e:
                    print(f"  ✗ Invalid JSON: {e}")
                    return False
            else:
                print(f"  ✗ Not JSON response: {body[:100]}...")
                return False
            
            if status_code == expected_status:
                print(f"  ✓ Success!\n")
                return True
            else:
                print(f"  ✗ Unexpected status code\n")
                return False
                
    except urllib.error.HTTPError as e:
        print(f"  ✗ HTTP Error {e.code}: {e.reason}")
        if e.code == expected_status:
            print(f"  ✓ Expected error status\n")
            return True
        print()
        return False
    except urllib.error.URLError as e:
        print(f"  ✗ URL Error: {e.reason}")
        print()
        return False
    except Exception as e:
        print(f"  ✗ Unexpected error: {e}")
        print()
        return False


def main():
    """Main testing function"""
    if len(sys.argv) > 1:
        base_url = sys.argv[1].rstrip("/")
    else:
        base_url = get_api_base_url()
    
    print(f"Testing health endpoints at {base_url}")
    print("=" * 50)
    
    endpoints = [
        ("/health/live", 200),
        ("/health/ready", None),  # 200 or 503 depending on services
        ("/health/beat", 200),
    ]
    
    success_count = 0
    total_count = len(endpoints)
    
    for endpoint, expected_status in endpoints:
        if expected_status is None:
            # ready エンドポイントは環境によって異なる
            success = (test_endpoint(base_url, endpoint, 200) or 
                      test_endpoint(base_url, endpoint, 503))
        else:
            success = test_endpoint(base_url, endpoint, expected_status)
        
        if success:
            success_count += 1
    
    print("=" * 50)
    print(f"Results: {success_count}/{total_count} tests passed")
    
    if success_count == total_count:
        print("✅ All health endpoints are working correctly!")
        sys.exit(0)
    else:
        print("❌ Some health endpoints failed!")
        sys.exit(1)


def test_docker_healthcheck():
    """Test the exact same command used in Docker healthcheck"""
    print("\nTesting Docker healthcheck command...")
    print("=" * 50)
    
    try:
        # Docker healthcheck と同じコマンドを実行
        import urllib.request
        url = build_api_url("health/live")
        print(f"Running: urllib.request.urlopen('{url}')")
        
        start_time = time.time()
        with urllib.request.urlopen(url) as response:
            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            
            status_code = response.getcode()
            body = response.read().decode('utf-8')
            
            print(f"✓ Status: {status_code}")
            print(f"✓ Response time: {response_time:.2f}ms")
            print(f"✓ Body: {body}")
            print("✅ Docker healthcheck command works!")
            return True
            
    except Exception as e:
        print(f"❌ Docker healthcheck command failed: {e}")
        return False


if __name__ == "__main__":
    main()
    test_docker_healthcheck()
