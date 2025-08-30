#!/usr/bin/env python3

import sys
import os
sys.path.append('/home/kyon/myproject')

from webapp.wiki.utils import process_plantuml_blocks

# 簡単なPlantUMLテスト
test_plantuml = """
```plantuml
@startuml
Alice -> Bob: Hello
Bob --> Alice: Hi!
@enduml
```
"""

print("=== 入力 ===")
print(test_plantuml)

print("\n=== PlantUML処理結果 ===")
result = process_plantuml_blocks(test_plantuml)
print(result)

# URLの部分だけを抽出
import re
url_match = re.search(r'src="__PLANTUML_URL__(.*?)__PLANTUML_URL__"', result)
if url_match:
    url = url_match.group(1)
    print(f"\n=== 生成されたURL ===")
    print(url)
    
    # ~1プレフィックスがあるかチェック
    if "/png/~1" in url:
        print("✅ ~1プレフィックスが正しく追加されています")
    else:
        print("❌ ~1プレフィックスが見つかりません")
else:
    print("❌ URLが見つかりませんでした")
