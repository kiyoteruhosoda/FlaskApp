#!/usr/bin/env python3
"""
PlantUMLエンコーディングの検証とテスト
"""

import sys
import os
sys.path.append('/home/kyon/myproject')

from webapp.wiki.utils import process_plantuml_blocks
import zlib
import base64
import requests

def test_plantuml_encoding():
    """PlantUMLエンコーディングのテスト"""
    
    # 簡単なテストケース
    test_cases = [
        {
            'name': 'Simple Hello World',
            'code': '@startuml\nAlice -> Bob: Hello World\n@enduml'
        },
        {
            'name': 'Class Diagram',
            'code': '@startuml\nclass User {\n  +name: string\n  +email: string\n}\n@enduml'
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n=== テストケース {i}: {test_case['name']} ===")
        
        # 現在の実装でエンコード
        uml_code = test_case['code']
        print(f"PlantUMLコード:\n{uml_code}")
        
        try:
            # UTF-8でエンコード
            utf8_bytes = uml_code.encode('utf-8')
            print(f"UTF-8バイト数: {len(utf8_bytes)}")
            
            # DEFLATEで圧縮（raw deflate）
            compressed = zlib.compress(utf8_bytes)[2:-4]  # zlib headerとtrailerを除去
            print(f"圧縮後バイト数: {len(compressed)}")
            
            # Base64URLでエンコード
            encoded = base64.urlsafe_b64encode(compressed).decode('ascii').rstrip('=')
            print(f"エンコード結果: {encoded}")
            
            # URL生成
            plantuml_url = f"https://www.plantuml.com/plantuml/png/{encoded}"
            print(f"PlantUML URL: {plantuml_url}")
            
            # URLの長さをチェック
            if len(plantuml_url) > 2048:
                print("⚠️  警告: URLが長すぎます（2048文字超）")
            else:
                print("✅ URL長さ: OK")
            
            # 実際のプロセス関数でテスト
            markdown_input = f"```plantuml\n{uml_code}\n```"
            result = process_plantuml_blocks(markdown_input)
            
            # 生成されたURLを抽出
            import re
            url_pattern = r'src="[^"]*https://www\.plantuml\.com/plantuml/png/([^"]*)"'
            matches = re.findall(url_pattern, result)
            if matches:
                actual_encoded = matches[0].replace('__PLANTUML_URL__', '')
                print(f"実際の生成結果: {actual_encoded}")
                if encoded == actual_encoded:
                    print("✅ エンコーディング一致")
                else:
                    print("❌ エンコーディング不一致")
            
        except Exception as e:
            print(f"❌ エラー: {e}")
            import traceback
            traceback.print_exc()

def test_original_vs_new_encoding():
    """元のエンコーディングと新しいエンコーディングの比較"""
    
    uml_code = "@startuml\nAlice -> Bob: Hello World\n@enduml"
    
    print("=== エンコーディング方式の比較 ===")
    
    # 元の方式（zlib.compress + base64）
    try:
        compressed_old = zlib.compress(uml_code.encode('utf-8'))
        encoded_old = base64.b64encode(compressed_old).decode('ascii')
        url_old = f"https://www.plantuml.com/plantuml/png/~1{encoded_old}"
        print(f"元の方式 (~1付き): {encoded_old[:50]}...")
        print(f"URL長さ: {len(url_old)}")
    except Exception as e:
        print(f"元の方式エラー: {e}")
    
    # 新しい方式（raw deflate + base64url）
    try:
        compressed_new = zlib.compress(uml_code.encode('utf-8'))[2:-4]
        encoded_new = base64.urlsafe_b64encode(compressed_new).decode('ascii').rstrip('=')
        url_new = f"https://www.plantuml.com/plantuml/png/{encoded_new}"
        print(f"新しい方式: {encoded_new[:50]}...")
        print(f"URL長さ: {len(url_new)}")
    except Exception as e:
        print(f"新しい方式エラー: {e}")

if __name__ == "__main__":
    test_original_vs_new_encoding()
    test_plantuml_encoding()
