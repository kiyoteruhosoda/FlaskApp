"""
Wiki機能用のユーティリティ関数
"""

import re
import markdown
from markupsafe import Markup
from datetime import datetime, timezone


def markdown_to_html(text):
    """MarkdownテキストをHTMLに変換"""
    if not text:
        return ""
    
    # Markdownエクステンションを設定
    md = markdown.Markdown(extensions=[
        'markdown.extensions.fenced_code',  # コードブロック
        'markdown.extensions.tables',       # テーブル
        'markdown.extensions.toc',          # 目次
        'markdown.extensions.codehilite',   # シンタックスハイライト
    ])
    
    html = md.convert(text)
    return Markup(html)


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
    
    # 日本語対応のスラッグ生成
    slug = title.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)  # 特殊文字を削除
    slug = re.sub(r'[-\s]+', '-', slug)   # スペースとハイフンを統一
    slug = slug.strip('-')                # 前後のハイフンを削除
    
    return slug


def highlight_search_term(text, term):
    """検索語句をハイライト"""
    if not text or not term:
        return text
    
    # 大文字小文字を区別しない検索
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    highlighted = pattern.sub(f'<mark>{term}</mark>', text)
    
    return Markup(highlighted)


def format_datetime(dt, format_str='%Y/%m/%d %H:%M'):
    """日時を指定されたフォーマットで文字列に変換"""
    if not dt:
        return ""
    
    # タイムゾーンを日本時間に変換（必要に応じて）
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    return dt.strftime(format_str)


def get_page_breadcrumb(page):
    """ページの階層パンくずリストを生成"""
    breadcrumb = []
    current_page = page
    
    while current_page:
        breadcrumb.insert(0, {
            'title': current_page.title,
            'slug': current_page.slug,
            'id': current_page.id
        })
        current_page = current_page.parent
    
    return breadcrumb


def extract_headings(markdown_text):
    """Markdownテキストから見出しを抽出してTOCを生成"""
    headings = []
    lines = markdown_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            if level <= 6:  # H1からH6まで
                title = line.lstrip('#').strip()
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
    if not slug:
        return False
    
    # 英数字、ハイフン、アンダースコアのみ許可
    pattern = r'^[a-zA-Z0-9_-]+$'
    return bool(re.match(pattern, slug))


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
}
