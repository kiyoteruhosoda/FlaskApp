#!/usr/bin/env python3
"""
PlantUMLライブラリのエンコーディング機能のみを使用
"""

def test_plantuml_encoding_only():
    """PlantUMLのエンコーディング機能のみをテスト"""
    
    try:
        import plantuml
        
        # PlantUMLインスタンスを作成（実際の通信は行わない）
        server = plantuml.PlantUML(url='https://www.plantuml.com/plantuml/img/')
        
        uml_code = "@startuml\nAlice -> Bob: Hello World\n@enduml"
        
        print("=== PlantUMLエンコーディングのみテスト ===")
        
        # エンコーディング部分だけを取得したい
        # get_urlは通信するので、別の方法を探す
        
        # ライブラリの内部メソッドを確認
        print("利用可能なメソッド:")
        for attr in dir(server):
            if not attr.startswith('_') and callable(getattr(server, attr)):
                print(f"  - {attr}")
                
        # _make_url や encode などのメソッドがあるかチェック
        if hasattr(server, '_make_url'):
            print("_make_url メソッドが存在します")
        if hasattr(server, 'encode'):
            print("encode メソッドが存在します")
            
        # ソースコードを参考に、直接エンコーディング関数を作成
        # PlantUMLの標準的なエンコーディング手順
        import zlib
        import string
        
        # PlantUML文字セット（標準）
        plantuml_alphabet = string.digits + string.ascii_uppercase + string.ascii_lowercase + '-_'
        
        def encode_plantuml_data(data):
            """PlantUMLのエンコーディング（ライブラリの実装を参考）"""
            compressed = zlib.compress(data.encode('utf-8'))
            
            # Base64的なエンコーディングではなく、PlantUML独自のエンコーディング
            # ただし、今回は標準的な方法を使用
            import base64
            encoded = base64.b64encode(compressed[2:-4]).decode('ascii')  # zlib headerを除去
            
            # URL安全文字に変換
            encoded = encoded.replace('+', '-').replace('/', '_').rstrip('=')
            
            return encoded
            
        # 手動エンコード
        manual_encoded = encode_plantuml_data(uml_code)
        manual_url = f"https://www.plantuml.com/plantuml/png/{manual_encoded}"
        
        print(f"\n手動エンコード結果: {manual_encoded}")
        print(f"手動URL: {manual_url}")
        
        # 比較のため、元の方式も試す
        compressed_orig = zlib.compress(uml_code.encode('utf-8'))
        encoded_orig = base64.b64encode(compressed_orig).decode('ascii')
        url_orig = f"https://www.plantuml.com/plantuml/png/~1{encoded_orig}"
        
        print(f"\n元の方式エンコード: {encoded_orig}")
        print(f"元の方式URL: {url_orig}")
        
        return manual_url, url_orig
        
    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
        return None, None

if __name__ == "__main__":
    test_plantuml_encoding_only()
