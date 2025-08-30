#!/usr/bin/env python3

try:
    import sys
    import os
    sys.path.append('/home/kyon/myproject')
    
    print("モジュールインポート中...")
    from webapp.wiki.utils import process_plantuml_blocks
    
    print("PlantUMLテスト開始...")
    test_input = """```plantuml
@startuml
Alice -> Bob: Hello World
@enduml
```"""
    
    result = process_plantuml_blocks(test_input)
    print("PlantUML処理結果:")
    print(result)
    
    # URLを検索
    import re
    if "~1" in result:
        print("\n✅ SUCCESS: ~1プレフィックスが見つかりました!")
    else:
        print("\n❌ ERROR: ~1プレフィックスがありません")
        
except Exception as e:
    print(f"エラー: {e}")
    import traceback
    traceback.print_exc()
