#!/usr/bin/env python3

import sys
import os
sys.path.append('/home/kyon/myproject')

from webapp.wiki.utils import markdown_to_html

# テストファイルを読み込み
with open('/home/kyon/myproject/test_diagrams_wiki.md', 'r', encoding='utf-8') as f:
    content = f.read()

# HTML変換
html_output = markdown_to_html(content)

# HTMLファイルに出力
html_page = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wiki図表テスト</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        .plantuml-diagram, .mermaid-diagram {{
            margin: 1rem 0;
            border: 1px solid #dee2e6;
            border-radius: 0.375rem;
            overflow: hidden;
        }}
        .diagram-header {{
            background-color: #f8f9fa;
            padding: 0.5rem 1rem;
            border-bottom: 1px solid #dee2e6;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .diagram-content {{
            padding: 1rem;
            text-align: center;
        }}
        .diagram-source {{
            background-color: #f8f9fa;
            border-top: 1px solid #dee2e6;
            display: none !important;
        }}
        .diagram-source.show {{
            display: block !important;
        }}
        .diagram-source pre {{
            margin: 0;
            background-color: transparent;
            border: none;
        }}
    </style>
</head>
<body>
    <div class="container mt-4">
        {html_output}
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js"></script>
    <script>
        // Mermaid初期化
        document.addEventListener('DOMContentLoaded', function() {{
            if (typeof mermaid !== 'undefined') {{
                mermaid.initialize({{
                    startOnLoad: true,
                    theme: 'default',
                    securityLevel: 'loose'
                }});
            }}
        }});

        // PlantUMLソース表示/非表示
        function togglePlantUMLSource(hash) {{
            const sourceDiv = document.getElementById('plantuml-source-' + hash);
            const button = event.target.closest('button');
            
            if (sourceDiv.classList.contains('show')) {{
                sourceDiv.classList.remove('show');
                button.innerHTML = '<i class="fas fa-code"></i>';
                button.title = 'ソースコードを表示';
            }} else {{
                sourceDiv.classList.add('show');
                button.innerHTML = '<i class="fas fa-eye-slash"></i>';
                button.title = 'ソースコードを非表示';
            }}
        }}

        // Mermaidソース表示/非表示
        function toggleMermaidSource(hash) {{
            const sourceDiv = document.getElementById('mermaid-source-' + hash);
            const button = event.target.closest('button');
            
            if (sourceDiv.classList.contains('show')) {{
                sourceDiv.classList.remove('show');
                button.innerHTML = '<i class="fas fa-code"></i>';
                button.title = 'ソースコードを表示';
            }} else {{
                sourceDiv.classList.add('show');
                button.innerHTML = '<i class="fas fa-eye-slash"></i>';
                button.title = 'ソースコードを非表示';
            }}
        }}
    </script>
</body>
</html>"""

with open('/home/kyon/myproject/test_diagrams_output.html', 'w', encoding='utf-8') as f:
    f.write(html_page)

print("HTMLファイルが生成されました: test_diagrams_output.html")
