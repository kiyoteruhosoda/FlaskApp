#!/usr/bin/env python3
"""
Wiki改行機能のテスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from features.wiki.presentation.wiki.utils import markdown_to_html

def test_single_newline():
    """単一改行のテスト"""
    test_text = """これは最初の行です。
これは2行目です。
これは3行目です。

これは空行の後の行です。"""
    
    result = markdown_to_html(test_text)
    print("入力:")
    print(repr(test_text))
    print("\n出力:")
    print(result)
    print("\n" + "="*50)

def test_code_block():
    """コードブロック内の改行テスト"""
    test_text = """普通のテキストです。
改行されるはずです。

```python
def test():
    print("これは")
    print("コードブロック")
    return True
```

再び普通のテキスト。
また改行されるはずです。"""
    
    result = markdown_to_html(test_text)
    print("コードブロックテスト入力:")
    print(repr(test_text))
    print("\n出力:")
    print(result)
    print("\n" + "="*50)

def test_list_and_headers():
    """リストと見出しのテスト"""
    test_text = """# 見出し1
これは見出しの下の文です。
改行されるはずです。

## 見出し2
- リスト項目1
- リスト項目2

普通のテキスト。
改行されるはずです。"""
    
    result = markdown_to_html(test_text)
    print("リストと見出しテスト入力:")
    print(repr(test_text))
    print("\n出力:")
    print(result)

if __name__ == "__main__":
    test_single_newline()
    test_code_block()
    test_list_and_headers()
