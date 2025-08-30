#!/usr/bin/env python3

# 直接URLテスト
import sys
import os
sys.path.append('/home/kyon/myproject')

from webapp.wiki.utils import process_plantuml_blocks
import re

test_content = """```plantuml
@startuml
Alice -> Bob: Hello
@enduml
```"""

result = process_plantuml_blocks(test_content)

# URLを抽出
url_pattern = r'src="[^"]*https://www\.plantuml\.com/plantuml/png/([^"]*)"'
matches = re.findall(url_pattern, result)

if matches:
    encoded_part = matches[0].replace('__PLANTUML_URL__', '')
    full_url = f"https://www.plantuml.com/plantuml/png/{encoded_part}"
    print(f"生成されたURL: {full_url}")
    
    # 簡単なHTMLファイルを生成
    html = f"""<!DOCTYPE html>
<html>
<head><title>PlantUMLテスト</title></head>
<body>
<h1>PlantUMLテスト</h1>
<p>URL: <a href="{full_url}">{full_url}</a></p>
<img src="{full_url}" alt="PlantUML" style="border:1px solid #ccc;">
</body>
</html>"""
    
    with open('/home/kyon/myproject/simple_plantuml_test.html', 'w') as f:
        f.write(html)
    
    print("✅ 簡単なテストファイルを生成しました: simple_plantuml_test.html")
else:
    print("❌ URLが見つかりませんでした")
