#!/usr/bin/env python3

import requests
import json

from shared.application.api_urls import build_api_url

# テスト用のMarkdownコンテンツ
test_content = """# 図表テストページ

## Mermaidフローチャート

```mermaid
graph TD
    A[開始] --> B{条件チェック}
    B -->|Yes| C[処理A]
    B -->|No| D[処理B]
    C --> E[終了]
    D --> E
```

## 通常のMarkdown

これは通常のテキストです。URLも認識されます：
https://example.com

- リスト1
- リスト2
"""

# プレビューAPIをテスト
url = build_api_url("wiki/api/preview")
headers = {"Content-Type": "application/json"}
data = {"content": test_content}

try:
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        result = response.json()
        print("プレビューAPI成功:")
        print(result["html"])
    else:
        print(f"エラー: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"リクエストエラー: {e}")
