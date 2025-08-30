#!/usr/bin/env python3

import sys
import os
sys.path.append('/home/kyon/myproject')

from webapp.wiki.utils import markdown_to_html

# テストファイルを読み込み
with open('/home/kyon/myproject/tests/test_diagrams_wiki.md', 'r', encoding='utf-8') as f:
    content = f.read()

print("=== 入力 ===")
print(content)
print("\n=== 出力 ===")

# HTML変換
html_output = markdown_to_html(content)
print(html_output)

print("\n=== 変換完了 ===")
