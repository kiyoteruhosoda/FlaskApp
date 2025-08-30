#!/usr/bin/env python3

import sys
import os
sys.path.append('/home/kyon/myproject')

print("=== PlantUMLデバッグ開始 ===")

try:
    print("1. モジュールインポート中...")
    from webapp.wiki.utils import process_plantuml_blocks
    print("✅ インポート成功")
    
    print("2. テストデータ準備中...")
    test_content = """```plantuml
@startuml
Alice -> Bob: Hello
@enduml
```"""
    print("✅ テストデータ準備完了")
    
    print("3. PlantUML処理開始...")
    result = process_plantuml_blocks(test_content)
    print("✅ PlantUML処理完了")
    
    print("4. 結果解析中...")
    import re
    url_pattern = r'src="[^"]*https://www\.plantuml\.com/plantuml/png/([^"]*)"'
    matches = re.findall(url_pattern, result)
    
    if matches:
        encoded_part = matches[0].replace('__PLANTUML_URL__', '')
        full_url = f"https://www.plantuml.com/plantuml/png/{encoded_part}"
        print(f"✅ URL生成成功: {full_url}")
    else:
        print("❌ URLが見つかりませんでした")
        print("結果:")
        print(result[:500] + "..." if len(result) > 500 else result)

except ImportError as e:
    print(f"❌ インポートエラー: {e}")
except Exception as e:
    print(f"❌ 予期しないエラー: {e}")
    import traceback
    traceback.print_exc()

print("=== デバッグ終了 ===")
