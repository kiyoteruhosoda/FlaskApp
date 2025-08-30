#!/usr/bin/env python3

# 簡単なテスト
test_content = """# PlantUMLテスト

```plantuml
@startuml
Alice -> Bob: Hello
Bob --> Alice: Hi there!
@enduml
```
"""

# 直接HTMLに変換
import sys
import os
sys.path.append('/home/kyon/myproject')

from webapp.wiki.utils import markdown_to_html

html_result = str(markdown_to_html(test_content))

# URLを抽出
import re
url_pattern = r'src="([^"]*plantuml[^"]*)"'
matches = re.findall(url_pattern, html_result)

print("生成されたPlantUML URL:")
for url in matches:
    print(url)
    if "~1" in url:
        print("✅ ~1プレフィックスが含まれています")
    else:
        print("❌ ~1プレフィックスがありません")

# HTMLファイルを生成
html_page = f"""<!DOCTYPE html>
<html>
<head>
    <title>PlantUML ~1プレフィックステスト</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .plantuml-diagram {{ margin: 20px 0; border: 1px solid #ddd; }}
        .diagram-header {{ background: #f8f9fa; padding: 10px; }}
        .diagram-content {{ padding: 20px; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        {html_result}
    </div>
    <script>
        function togglePlantUMLSource(hash) {{
            const sourceDiv = document.getElementById('plantuml-source-' + hash);
            const button = event.target.closest('button');
            
            if (sourceDiv.style.display === 'none') {{
                sourceDiv.style.display = 'block';
                button.innerHTML = '<i class="fas fa-eye-slash"></i>';
            }} else {{
                sourceDiv.style.display = 'none';
                button.innerHTML = '<i class="fas fa-code"></i>';
            }}
        }}
    </script>
</body>
</html>"""

with open('/home/kyon/myproject/plantuml_test.html', 'w', encoding='utf-8') as f:
    f.write(html_page)

print("\nHTMLファイルが生成されました: plantuml_test.html")
