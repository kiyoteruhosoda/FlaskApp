"""Domain services and value objects for processing wiki markdown content.

このモジュールは、Wiki ドメインにおける Markdown コンテンツの加工処理を
オブジェクト指向的に表現する。従来 `webapp/wiki/utils.py` に散在していた
手続き的な関数を、ドメインサービス/値オブジェクトへと整理することで
DDD の設計指針に沿った責務分割を実現する。
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
from dataclasses import dataclass
from typing import Callable

import markdown


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarkdownContent:
    """Markdown 形式の本文を表す値オブジェクト。"""

    value: str

    def normalized(self) -> str:
        """None や空文字を考慮した正規化済みテキストを返す。"""

        return (self.value or "").strip("\ufeff")

    def is_empty(self) -> bool:
        return not self.normalized()


class UrlAutoLinker:
    """テキスト中の URL を自動的にリンク化するコンポーネント。"""

    _HTML_LINK_PATTERN = re.compile(r'<a\s[^>]*href=["\'][^"\']*["\'][^>]*>.*?</a>', re.IGNORECASE | re.DOTALL)
    _MARKDOWN_LINK_PATTERN = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
    _HTML_ATTR_PATTERN = re.compile(r'(?:src|href|action|data-[^=]*)\s*=\s*["\'][^"\']*https?://[^"\']*["\']', re.IGNORECASE)
    _URL_PATTERN = re.compile(r'(https?://(?:\[[0-9a-fA-F:]+\]|[^\s<>"\'`\]]+)(?::[0-9]+)?[^\s<>"\'`]*)')

    def convert(self, text: str) -> str:
        if not text:
            return ""

        placeholders: dict[str, str] = {}
        placeholder_pattern = "___TEMP_LINK_{}_TEMP___"
        counter = 0

        def _store(match: re.Match[str]) -> str:
            nonlocal counter
            placeholder = placeholder_pattern.format(counter)
            placeholders[placeholder] = match.group(0)
            counter += 1
            return placeholder

        # 既存のリンク/属性を一時的に退避する
        text = self._HTML_LINK_PATTERN.sub(_store, text)
        text = self._MARKDOWN_LINK_PATTERN.sub(_store, text)
        text = self._HTML_ATTR_PATTERN.sub(_store, text)

        def _replace(match: re.Match[str]) -> str:
            url = re.sub(r'[.,;!?]+$', '', match.group(1))
            return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'

        text = self._URL_PATTERN.sub(_replace, text)

        for placeholder, original in placeholders.items():
            text = text.replace(placeholder, original)

        return text


class SingleNewlineProcessor:
    """Markdown の改行ルールを補助する前処理コンポーネント。"""

    def apply(self, text: str) -> str:
        if not text:
            return ""

        text = text.replace('\r\n', '\n').replace('\r', '\n')
        lines = text.split('\n')
        result_lines: list[str] = []
        in_fenced_code = False

        for idx, line in enumerate(lines):
            if line.strip().startswith('```'):
                in_fenced_code = not in_fenced_code
                result_lines.append(line)
                continue

            if in_fenced_code:
                result_lines.append(line)
                continue

            if (
                idx + 1 < len(lines)
                and line.strip()
                and lines[idx + 1].strip()
                and not lines[idx + 1].startswith('#')
                and not line.endswith('  ')
            ):
                result_lines.append(line + '  ')
            else:
                result_lines.append(line)

        return '\n'.join(result_lines)


class MermaidDiagramProcessor:
    """Mermaid 記法のコードブロックを HTML に変換する。"""

    _PATTERN = re.compile(r'```mermaid\s*\n(.*?)\n```', re.DOTALL)

    def process(self, text: str) -> str:
        if not text:
            return ""

        def _replace(match: re.Match[str]) -> str:
            mermaid_code = match.group(1).strip()
            if not mermaid_code:
                return match.group(0)

            code_hash = hashlib.md5(mermaid_code.encode('utf-8')).hexdigest()[:8]
            return (
                f"<div class=\"mermaid-diagram\" data-hash=\"{code_hash}\">\n"
                "    <div class=\"diagram-header\">\n"
                "        <small class=\"text-muted\">Mermaid Diagram</small>\n"
                "        <button class=\"btn btn-sm btn-outline-secondary ms-2\"\n"
                f"                onclick=\"toggleMermaidSource('{code_hash}')\"\n"
                "                title=\"ソースコードを表示/非表示\">\n"
                "            <i class=\"fas fa-code\"></i>\n"
                "        </button>\n"
                "    </div>\n"
                "    <div class=\"diagram-content\">\n"
                f"        <div class=\"mermaid\" id=\"mermaid-{code_hash}\">\n"
                f"{html.escape(mermaid_code)}\n"
                "        </div>\n"
                "    </div>\n"
                f"    <div class=\"diagram-source\" id=\"mermaid-source-{code_hash}\">\n"
                f"        <pre><code class=\"language-mermaid\">{html.escape(mermaid_code)}</code></pre>\n"
                "    </div>\n"
                "</div>"
            )

        return self._PATTERN.sub(_replace, text)


class HtmlEscaper:
    """Markdown 入力中の危険な HTML をサニタイズする。"""

    def escape(self, text: str) -> str:
        if not text:
            return ""

        lines = text.split('\n')
        result_lines: list[str] = []
        in_fenced_code = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('```'):
                in_fenced_code = not in_fenced_code
                result_lines.append(line)
                continue

            if in_fenced_code:
                result_lines.append(line)
                continue

            if line.startswith('    ') or line.startswith('\t'):
                result_lines.append(line)
            else:
                result_lines.append(line.replace('<', '&lt;').replace('>', '&gt;'))

        return '\n'.join(result_lines)


class HtmlSanitizer:
    """Markdown 変換後の HTML から危険な要素を取り除く。"""

    _DANGEROUS_TAGS = [
        'script', 'iframe', 'object', 'embed', 'applet',
        'form', 'input', 'button', 'textarea', 'select',
        'meta', 'link', 'style', 'base', 'frame', 'frameset',
    ]

    _DANGEROUS_ATTRS = [
        'onload', 'onerror', 'onmouseover', 'onmouseout',
        'onfocus', 'onblur', 'onchange', 'onsubmit', 'onreset',
        'onkeydown', 'onkeyup', 'onkeypress', 'onmousedown', 'onmouseup',
        'javascript:', 'vbscript:', 'data:',
    ]

    _DIAGRAM_PATTERN = re.compile(r'<div class="mermaid-diagram"[^>]*>.*?</div>', re.DOTALL)

    def clean(self, html_content: str) -> str:
        if not html_content:
            return ""

        placeholders: dict[str, str] = {}
        counter = 0

        for match in self._DIAGRAM_PATTERN.finditer(html_content):
            placeholder = f"___DIAGRAM_PLACEHOLDER_{counter}_DIAGRAM___"
            placeholders[placeholder] = match.group(0)
            html_content = html_content.replace(match.group(0), placeholder)
            counter += 1

        for tag in self._DANGEROUS_TAGS:
            pattern = re.compile(rf'<\s*{tag}[^>]*>.*?<\s*/\s*{tag}\s*>', re.IGNORECASE | re.DOTALL)
            html_content = pattern.sub('', html_content)
            pattern = re.compile(rf'<\s*{tag}[^>]*/?>', re.IGNORECASE)
            html_content = pattern.sub('', html_content)

        for attr in self._DANGEROUS_ATTRS:
            if attr.endswith(':'):
                pattern = re.compile(rf'{attr}[^"\'\s>]*', re.IGNORECASE)
            else:
                pattern = re.compile(rf'{attr}\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)
            html_content = pattern.sub('', html_content)

        onclick_pattern = re.compile(r'onclick\s*=\s*["\'](?!toggleMermaidSource)[^"\']*["\']', re.IGNORECASE)
        html_content = onclick_pattern.sub('', html_content)

        for placeholder, original_html in placeholders.items():
            html_content = html_content.replace(placeholder, original_html)

        return html_content


class MarkdownRenderer:
    """Wiki 向け Markdown レンダラー。"""

    def __init__(
        self,
        *,
        auto_linker: UrlAutoLinker | None = None,
        preprocessor: SingleNewlineProcessor | None = None,
        sanitizer: HtmlSanitizer | None = None,
        diagram_processor: MermaidDiagramProcessor | None = None,
        html_escaper: HtmlEscaper | None = None,
        markdown_factory: Callable[[], markdown.Markdown] | None = None,
    ) -> None:
        self.auto_linker = auto_linker or UrlAutoLinker()
        self.preprocessor = preprocessor or SingleNewlineProcessor()
        self.sanitizer = sanitizer or HtmlSanitizer()
        self.diagram_processor = diagram_processor or MermaidDiagramProcessor()
        self.html_escaper = html_escaper or HtmlEscaper()
        self._markdown_factory = markdown_factory or self._default_markdown_factory

    @staticmethod
    def _default_markdown_factory() -> markdown.Markdown:
        return markdown.Markdown(
            extensions=[
                'markdown.extensions.fenced_code',
                'markdown.extensions.tables',
                'markdown.extensions.toc',
                'markdown.extensions.codehilite',
            ]
        )

    def render(self, content: MarkdownContent) -> str:
        if content.is_empty():
            logger.debug("Markdown content is empty; returning empty string")
            return ""

        logger.debug("Rendering markdown content: %s", content.normalized()[:100])

        text = self.html_escaper.escape(content.normalized())
        text = self.diagram_processor.process(text)
        text = self.preprocessor.apply(text)

        engine = self._markdown_factory()
        html_output = engine.convert(text)

        sanitized = self.sanitizer.clean(html_output)
        linked = self.auto_linker.convert(sanitized)

        logger.debug("Rendered HTML output: %s", linked[:100])
        return linked

