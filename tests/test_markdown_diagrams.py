"""MarkdownのMermaid図表変換のテスト"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

# リポジトリルートをパスに追加
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from features.wiki.presentation.wiki.utils import markdown_to_html

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "test_diagrams_wiki.md"


def test_mermaid_block_is_converted_to_html():
    """MermaidコードブロックがHTMLに変換されることを確認する"""
    content = FIXTURE_PATH.read_text(encoding="utf-8")

    html_output = markdown_to_html(content)
    html_str = str(html_output)

    mermaid_code = "graph TD;\n    A-->B;\n    B-->C;"
    code_hash = hashlib.md5(mermaid_code.encode("utf-8")).hexdigest()[:8]

    assert f'<div class="mermaid-diagram" data-hash="{code_hash}">' in html_str
    assert f'id="mermaid-{code_hash}"' in html_str
    assert "toggleMermaidSource" in html_str
    assert "Mermaid Diagram" in html_str
    assert '<pre><code class="language-mermaid">' in html_str
    assert 'graph TD;' in html_str
    assert 'A--&gt;B;' in html_str
    assert 'B--&gt;C;' in html_str
    assert '</code></pre>' in html_str
    assert "```" not in html_str


def test_non_diagram_text_is_preserved():
    """Mermaid以外のテキストがそのままHTMLに残ることを確認する"""
    content = FIXTURE_PATH.read_text(encoding="utf-8")

    html_output = markdown_to_html(content)
    html_str = str(html_output)

    assert "図表テスト" in html_str
    assert "テスト終了。" in html_str
    # 自動改行処理により<p>タグ内に保持されていることを確認
    assert "以下はMermaidのサンプルです。" in html_str

