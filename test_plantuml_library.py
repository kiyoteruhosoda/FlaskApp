#!/usr/bin/env python3
"""
PlantUMLライブラリを使用したテスト
"""

import plantuml

def test_plantuml_library():
    """plantumlライブラリの機能をテスト"""
    
    # 簡単なPlantUMLコード
    uml_code = """
@startuml
Alice -> Bob: Hello World
@enduml
"""
    
    print("=== PlantUMLライブラリテスト ===")
    
    try:
        # plantumlライブラリのメソッドを確認
        print("利用可能なメソッド:")
        for attr in dir(plantuml):
            if not attr.startswith('_'):
                print(f"  - {attr}")
        
        # PlantUMLサーバーを使用
        if hasattr(plantuml, 'PlantUML'):
            server = plantuml.PlantUML(url='https://www.plantuml.com/plantuml/')
            print(f"\nPlantUMLサーバー: {server.url}")
            
            # URLを生成
            if hasattr(server, 'get_url'):
                url = server.get_url(uml_code)
                print(f"生成URL: {url}")
            
        # エンコーディング機能をテスト
        if hasattr(plantuml, 'deflate_and_encode'):
            encoded = plantuml.deflate_and_encode(uml_code)
            print(f"エンコード結果: {encoded}")
            
    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_plantuml_library()
