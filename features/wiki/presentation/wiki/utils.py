"""Wiki 機能で利用するユーティリティ群。"""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone

from flask import g
from markupsafe import Markup

from features.wiki.domain.markdown import (
    HtmlEscaper,
    HtmlSanitizer,
    MarkdownContent,
    MarkdownRenderer,
    MermaidDiagramProcessor,
    SingleNewlineProcessor,
    UrlAutoLinker,
)
from features.wiki.domain.slug import SlugService

from webapp.timezone import convert_to_timezone


logger = logging.getLogger(__name__)


# ドメイン層のサービス/値オブジェクトを初期化し、再利用する
_auto_linker = UrlAutoLinker()
_newline_processor = SingleNewlineProcessor()
_sanitizer = HtmlSanitizer()
_diagram_processor = MermaidDiagramProcessor()
_html_escaper = HtmlEscaper()
_slug_service = SlugService()
_renderer = MarkdownRenderer(
    auto_linker=_auto_linker,
    preprocessor=_newline_processor,
    sanitizer=_sanitizer,
    diagram_processor=_diagram_processor,
    html_escaper=_html_escaper,
)


def auto_link_urls(text: str | None) -> str:
    """テキスト中の URL を自動でリンク化する。"""

    return _auto_linker.convert(text or "")


def preprocess_single_newlines(text: str | None) -> str:
    """単一改行を Markdown の強制改行へ変換する。"""

    return _newline_processor.apply(text or "")


def sanitize_html(html_content: str | None) -> str:
    """HTML から危険な要素を除去する。"""

    return _sanitizer.clean(html_content or "")


def process_mermaid_blocks(text: str | None) -> str:
    """Mermaid 記法のコードブロックを HTML に変換する。"""

    return _diagram_processor.process(text or "")


def escape_user_html(text: str | None) -> str:
    """Markdown 入力中の危険な HTML をエスケープする。"""

    return _html_escaper.escape(text or "")


def markdown_to_html(text: str | None) -> Markup:
    """Markdown テキストを安全な HTML へ変換する。"""

    if not text:
        return Markup("")

    logger.debug("markdown_to_html input: %s", text[:100])
    rendered = _renderer.render(MarkdownContent(text))
    logger.debug("markdown_to_html output: %s", rendered[:100])
    return Markup(rendered)


def nl2br(text):
    """改行を<br>タグに変換"""
    if not text:
        return ""
    
    return Markup(text.replace('\n', '<br>'))


def truncate_text(text, length=100):
    """テキストを指定した長さで切り詰める"""
    if not text:
        return ""
    
    if len(text) <= length:
        return text
    
    return text[:length] + "..."


def generate_slug(title):
    """タイトルからスラッグを生成"""
    if not title:
        return ""

    try:
        return _slug_service.generate_from_text(title).value
    except ValueError:
        return ""


def format_datetime(dt):
    """日時をフォーマット"""
    if not dt:
        return ""

    if isinstance(dt, str):
        return dt

    tzinfo = getattr(g, "user_timezone", timezone.utc)
    localized = convert_to_timezone(dt, tzinfo)
    if localized is None:
        return ""
    return localized.strftime('%Y/%m/%d %H:%M')


def highlight_search_term(text, term):
    """検索語をハイライト"""
    if not text or not term:
        return text
    
    # HTMLエスケープしてからハイライト
    escaped_text = html.escape(str(text))
    escaped_term = html.escape(str(term))
    
    # 大文字小文字を区別しないハイライト
    pattern = re.compile(re.escape(escaped_term), re.IGNORECASE)
    highlighted = pattern.sub(f'<mark>{escaped_term}</mark>', escaped_text)
    
    return Markup(highlighted)


def extract_headings(markdown_text):
    """Markdownテキストから見出しを抽出してTOCを生成"""
    if not markdown_text:
        return []
    
    lines = markdown_text.split('\n')
    headings = []
    
    for line in lines:
        line = line.strip()
        if line.startswith('#'):
            # 見出しレベルを取得
            level = 0
            for char in line:
                if char == '#':
                    level += 1
                else:
                    break
            
            if level <= 6:  # H1-H6のみ
                title = line[level:].strip()
                if title:
                    # スラッグを生成（アンカーリンク用）
                    slug = generate_slug(title)
                    headings.append({
                        'level': level,
                        'title': title,
                        'slug': slug
                    })
    
    return headings


def word_count(text):
    """テキストの文字数をカウント"""
    if not text:
        return 0
    
    # HTMLタグを除去してから文字数カウント
    text = re.sub(r'<[^>]+>', '', text)
    return len(text.strip())


def reading_time(text, wpm=200):
    """読書時間を推定（分）"""
    if not text:
        return 0
    
    words = word_count(text)
    return max(1, round(words / wpm))


def validate_slug(slug):
    """スラッグの妥当性をチェック"""
    return _slug_service.is_valid(slug)


def sanitize_filename(filename):
    """ファイル名から危険な文字を除去"""
    if not filename:
        return ""
    
    # 危険な文字を除去または置換
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = re.sub(r'\.\.+', '.', filename)  # 連続するドットを単一に
    
    return filename.strip()


# Jinja2テンプレート用フィルタとして登録する関数リスト
TEMPLATE_FILTERS = {
    'markdown': markdown_to_html,
    'nl2br': nl2br,
    'truncate_text': truncate_text,
    'highlight_search': highlight_search_term,
    'format_datetime': format_datetime,
    'word_count': word_count,
    'reading_time': reading_time,
    'auto_link_urls': auto_link_urls,
}
