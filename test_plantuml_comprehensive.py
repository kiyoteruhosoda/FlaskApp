#!/usr/bin/env python3
"""
生成されたPlantUML URLが実際に動作するかテスト
"""

import sys
import os
sys.path.append('/home/kyon/myproject')

from webapp.wiki.utils import process_plantuml_blocks
import re

def generate_test_html():
    """テスト用のHTMLを生成"""
    
    test_cases = [
        {
            'title': 'Simple Sequence Diagram',
            'code': '''@startuml
Alice -> Bob: Hello World
Bob --> Alice: Hi there!
@enduml'''
        },
        {
            'title': 'Class Diagram',
            'code': '''@startuml
class User {
  +name: string
  +email: string
  +getId(): int
}

class Post {
  +title: string
  +content: string
  +author: User
}

User ||--o{ Post : "creates"
@enduml'''
        },
        {
            'title': 'Activity Diagram',
            'code': '''@startuml
start
:User login;
if (Valid credentials?) then (yes)
  :Grant access;
else (no)
  :Show error;
endif
stop
@enduml'''
        }
    ]
    
    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>PlantUML新エンコーディングテスト</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .test-case { margin: 30px 0; border: 1px solid #ddd; border-radius: 8px; }
        .test-header { background: #f8f9fa; padding: 15px; border-bottom: 1px solid #ddd; }
        .test-content { padding: 20px; }
        .plantuml-diagram { margin: 20px 0; border: 1px solid #ddd; }
        .diagram-header { background: #f8f9fa; padding: 10px; }
        .diagram-content { padding: 20px; text-align: center; }
        .diagram-source { background: #f8f9fa; padding: 15px; margin-top: 10px; }
        .url-info { background: #e3f2fd; padding: 10px; margin: 10px 0; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mt-4">PlantUML新エンコーディングテスト</h1>
        <div class="alert alert-info">
            <strong>テスト内容:</strong> ~1プレフィックスを削除した新しいDEFLATE + Base64URLエンコーディング
        </div>
"""
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"テストケース {i}: {test_case['title']}")
        
        # Markdownテキストを生成
        markdown_text = f"```plantuml\n{test_case['code']}\n```"
        
        # HTMLに変換
        html_result = process_plantuml_blocks(markdown_text)
        
        # URLを抽出
        url_pattern = r'src="[^"]*https://www\.plantuml\.com/plantuml/png/([^"]*)"'
        matches = re.findall(url_pattern, html_result)
        
        if matches:
            encoded_part = matches[0].replace('__PLANTUML_URL__', '')
            full_url = f"https://www.plantuml.com/plantuml/png/{encoded_part}"
            
            # プレースホルダーを実際のURLに置換
            html_result = html_result.replace('__PLANTUML_URL__', '')
            
            html_content += f"""
        <div class="test-case">
            <div class="test-header">
                <h3>テストケース {i}: {test_case['title']}</h3>
            </div>
            <div class="test-content">
                <div class="url-info">
                    <strong>生成URL:</strong><br>
                    <a href="{full_url}" target="_blank">{full_url}</a><br>
                    <small>エンコード部分: <code>{encoded_part}</code></small>
                </div>
                {html_result}
                <div class="mt-3">
                    <button class="btn btn-sm btn-outline-primary" onclick="testUrl{i}()">URLを直接テスト</button>
                    <div id="test-result-{i}" class="mt-2"></div>
                </div>
            </div>
        </div>"""
        else:
            print(f"  ❌ URLが見つかりませんでした")
    
    html_content += """
    </div>
    
    <script>
        function togglePlantUMLSource(hash) {
            const sourceDiv = document.getElementById('plantuml-source-' + hash);
            const button = event.target.closest('button');
            
            if (sourceDiv.style.display === 'none') {
                sourceDiv.style.display = 'block';
                button.innerHTML = '<i class="fas fa-eye-slash"></i>';
            } else {
                sourceDiv.style.display = 'none';
                button.innerHTML = '<i class="fas fa-code"></i>';
            }
        }
        
        function testUrl1() { testPlantUMLUrl(1, '""" + test_cases[0]['code'].replace('\n', '\\n').replace("'", "\\'") + """'); }
        function testUrl2() { testPlantUMLUrl(2, '""" + test_cases[1]['code'].replace('\n', '\\n').replace("'", "\\'") + """'); }
        function testUrl3() { testPlantUMLUrl(3, '""" + test_cases[2]['code'].replace('\n', '\\n').replace("'", "\\'") + """'); }
        
        function testPlantUMLUrl(testId, originalCode) {
            const resultDiv = document.getElementById('test-result-' + testId);
            resultDiv.innerHTML = '<div class="alert alert-info">URLをテスト中...</div>';
            
            // 同じページ内のイメージを確認
            const img = document.querySelector('.test-case:nth-child(' + (testId + 1) + ') img');
            if (img) {
                const testImg = new Image();
                testImg.onload = function() {
                    resultDiv.innerHTML = '<div class="alert alert-success">✅ URLは正常に動作します（画像サイズ: ' + this.width + 'x' + this.height + 'px）</div>';
                };
                testImg.onerror = function() {
                    resultDiv.innerHTML = '<div class="alert alert-danger">❌ URLでエラーが発生しました</div>';
                };
                testImg.src = img.src;
            }
        }
    </script>
</body>
</html>"""
    
    # HTMLファイルを保存
    with open('/home/kyon/myproject/plantuml_encoding_test.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("\n✅ テストHTMLファイルが生成されました: plantuml_encoding_test.html")
    print("ブラウザで開いて画像が正しく表示されるか確認してください。")

if __name__ == "__main__":
    generate_test_html()
