#!/usr/bin/env python3
"""
plantumlライブラリを使用した正しいエンコーディングテスト
"""

import plantuml

def test_with_plantuml_library():
    """plantumlライブラリを使用してURLを生成"""
    
    uml_code = """@startuml
Alice -> Bob: Hello World
@enduml"""
    
    print("=== PlantUMLライブラリを使用したテスト ===")
    
    try:
        # PlantUMLサーバーに接続
        server = plantuml.PlantUML(url='https://www.plantuml.com/plantuml/img/')
        
        print(f"サーバーURL: {server.url}")
        
        # URLを生成
        diagram_url = server.get_url(uml_code)
        print(f"生成されたURL: {diagram_url}")
        
        # 画像を取得してみる
        response = server.processes(uml_code)
        print(f"サーバーレスポンス型: {type(response)}")
        print(f"レスポンス長: {len(response) if response else 'None'}")
        
        return diagram_url
        
    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_manual_encoding():
    """手動でエンコーディングを実装"""
    
    uml_code = "@startuml\nAlice -> Bob: Hello World\n@enduml"
    
    print("\n=== 手動エンコーディングテスト ===")
    
    try:
        import zlib
        import base64
        
        # PlantUMLの標準エンコーディング
        # 1. UTF-8エンコード
        text_bytes = uml_code.encode('utf-8')
        
        # 2. zlib圧縮
        compressed = zlib.compress(text_bytes)
        
        # 3. Base64エンコード
        encoded = base64.b64encode(compressed).decode('ascii')
        
        # 4. URLを生成（~1プレフィックス付き）
        url = f"https://www.plantuml.com/plantuml/png/~1{encoded}"
        
        print(f"手動エンコードURL: {url}")
        print(f"エンコード部分: ~1{encoded}")
        
        return url
        
    except Exception as e:
        print(f"手動エンコードエラー: {e}")
        return None

if __name__ == "__main__":
    lib_url = test_with_plantuml_library()
    manual_url = test_manual_encoding()
    
    print("\n=== 結果比較 ===")
    print(f"ライブラリURL: {lib_url}")
    print(f"手動URL: {manual_url}")
    
    if lib_url and manual_url:
        print(f"URL一致: {lib_url == manual_url}")
