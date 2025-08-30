#!/usr/bin/env python3
"""
PlantUMLの正しいエンコーディングを実装するテスト
公式のPlantUML Text Encodingに基づく
"""

import zlib
import base64

def plantuml_encode_standard(plantuml_text):
    """
    PlantUMLの標準エンコーディング（公式仕様準拠）
    """
    # UTF-8エンコード
    utf8_bytes = plantuml_text.encode('utf-8')
    
    # Deflate圧縮（zlib形式ではなくraw deflate）
    # zlib.compress()はzlibヘッダー付きなので、raw deflateを作成
    compressed = zlib.compress(utf8_bytes, level=9)[2:-4]  # ヘッダーとフッターを削除
    
    # Base64エンコード（標準Base64、URL-safeではない）
    encoded = base64.b64encode(compressed).decode('ascii')
    
    return encoded

def plantuml_encode_url_safe(plantuml_text):
    """
    PlantUMLのURL-safeエンコーディング
    """
    # UTF-8エンコード
    utf8_bytes = plantuml_text.encode('utf-8')
    
    # Deflate圧縮
    compressed = zlib.compress(utf8_bytes, level=9)[2:-4]
    
    # Base64URL エンコード（パディング削除）
    encoded = base64.urlsafe_b64encode(compressed).decode('ascii').rstrip('=')
    
    return encoded

def plantuml_encode_hexadecimal(plantuml_text):
    """
    PlantUMLの16進エンコーディング（~hプレフィックス用）
    """
    # UTF-8エンコード
    utf8_bytes = plantuml_text.encode('utf-8')
    
    # 16進数に変換
    hex_encoded = utf8_bytes.hex().upper()
    
    return hex_encoded

def test_all_encoding_methods():
    """
    すべてのエンコーディング方法をテスト
    """
    test_uml = "@startuml\nAlice -> Bob: Hello World\n@enduml"
    
    print("=== PlantUMLエンコーディング方式テスト ===")
    print(f"入力テキスト: {test_uml}")
    print()
    
    # 方式1: 標準Deflate + Base64 (~1プレフィックス)
    try:
        encoded1 = plantuml_encode_standard(test_uml)
        url1 = f"https://www.plantuml.com/plantuml/png/~1{encoded1}"
        print(f"方式1 (Deflate+Base64, ~1): {encoded1[:50]}...")
        print(f"URL: {url1}")
        print(f"URL長さ: {len(url1)}")
        print()
    except Exception as e:
        print(f"方式1エラー: {e}")
    
    # 方式2: URL-safe Base64
    try:
        encoded2 = plantuml_encode_url_safe(test_uml)
        url2 = f"https://www.plantuml.com/plantuml/png/{encoded2}"
        print(f"方式2 (Deflate+Base64URL): {encoded2[:50]}...")
        print(f"URL: {url2}")
        print(f"URL長さ: {len(url2)}")
        print()
    except Exception as e:
        print(f"方式2エラー: {e}")
    
    # 方式3: 16進エンコーディング (~hプレフィックス)
    try:
        encoded3 = plantuml_encode_hexadecimal(test_uml)
        url3 = f"https://www.plantuml.com/plantuml/png/~h{encoded3}"
        print(f"方式3 (Hex, ~h): {encoded3[:50]}...")
        print(f"URL: {url3}")
        print(f"URL長さ: {len(url3)}")
        print()
    except Exception as e:
        print(f"方式3エラー: {e}")
    
    # 方式4: 元のzlib.compress（参考）
    try:
        compressed4 = zlib.compress(test_uml.encode('utf-8'))
        encoded4 = base64.b64encode(compressed4).decode('ascii')
        url4 = f"https://www.plantuml.com/plantuml/png/~1{encoded4}"
        print(f"方式4 (zlib+Base64, ~1): {encoded4[:50]}...")
        print(f"URL: {url4}")
        print(f"URL長さ: {len(url4)}")
        print()
    except Exception as e:
        print(f"方式4エラー: {e}")

def create_test_html():
    """
    複数のエンコーディング方式でテストHTMLを生成
    """
    test_uml = "@startuml\nAlice -> Bob: Hello World\n@enduml"
    
    # 各方式でエンコード
    methods = []
    
    try:
        encoded1 = plantuml_encode_standard(test_uml)
        methods.append(("Deflate+Base64 (~1)", f"https://www.plantuml.com/plantuml/png/~1{encoded1}"))
    except:
        pass
    
    try:
        encoded2 = plantuml_encode_url_safe(test_uml)
        methods.append(("Deflate+Base64URL", f"https://www.plantuml.com/plantuml/png/{encoded2}"))
    except:
        pass
    
    try:
        encoded3 = plantuml_encode_hexadecimal(test_uml)
        methods.append(("Hexadecimal (~h)", f"https://www.plantuml.com/plantuml/png/~h{encoded3}"))
    except:
        pass
    
    try:
        compressed4 = zlib.compress(test_uml.encode('utf-8'))
        encoded4 = base64.b64encode(compressed4).decode('ascii')
        methods.append(("zlib+Base64 (~1)", f"https://www.plantuml.com/plantuml/png/~1{encoded4}"))
    except:
        pass
    
    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>PlantUMLエンコーディング方式比較テスト</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .method { border: 1px solid #ccc; margin: 20px 0; padding: 15px; border-radius: 5px; }
        .method h3 { margin-top: 0; color: #333; }
        .url { background: #f5f5f5; padding: 10px; border-radius: 3px; word-break: break-all; margin: 10px 0; }
        img { max-width: 100%; border: 1px solid #ddd; margin: 10px 0; }
        .error { color: red; }
        .success { color: green; }
    </style>
</head>
<body>
    <h1>PlantUMLエンコーディング方式比較テスト</h1>
    <p><strong>テスト対象:</strong> <code>@startuml\\nAlice -> Bob: Hello World\\n@enduml</code></p>
"""
    
    for i, (method_name, url) in enumerate(methods, 1):
        html_content += f"""
    <div class="method">
        <h3>方式{i}: {method_name}</h3>
        <div class="url">
            <strong>URL:</strong> <a href="{url}" target="_blank">{url}</a>
        </div>
        <div>
            <strong>結果:</strong><br>
            <img src="{url}" alt="PlantUML図表 - {method_name}" 
                 onload="this.nextElementSibling.innerHTML='<span class=\\"success\\">✅ 成功: 画像が読み込まれました</span>'"
                 onerror="this.nextElementSibling.innerHTML='<span class=\\"error\\">❌ 失敗: 画像の読み込みに失敗しました</span>'">
            <div>読み込み中...</div>
        </div>
    </div>"""
    
    html_content += """
</body>
</html>"""
    
    with open('/home/kyon/myproject/plantuml_methods_test.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("✅ テストHTMLファイルが生成されました: plantuml_methods_test.html")

if __name__ == "__main__":
    test_all_encoding_methods()
    print("\n" + "="*50)
    create_test_html()
