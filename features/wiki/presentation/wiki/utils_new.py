"""
Wiki機能用のユーティリティ関数
"""

import re
import markdown
from markupsafe import Markup
from datetime import datetime, timezone
import html


def auto_link_urls(text):
    """http:やhttps:で始まるURLを自動的にリンクに変換"""
    if not text:
        return ""
    
    # すでにHTMLリンクやMarkdownリンクになっているものを除外してURLを自動リンク化
    
    # まず、すでにリンクになっているものを一時的に置換
    temp_replacements = {}
    placeholder_pattern = "___TEMP_LINK_{}_TEMP___"
    
    # HTMLリンクを保護
    html_link_pattern = r'<a\s[^>]*href=["\'][^"\']*["\'][^>]*>.*?</a>'
    counter = 0
    for match in re.finditer(html_link_pattern, text, re.IGNORECASE | re.DOTALL):
        placeholder = placeholder_pattern.format(counter)
        temp_replacements[placeholder] = match.group(0)
        text = text.replace(match.group(0), placeholder)
        counter += 1
    
    # Markdownリンクを保護
    md_link_pattern = r'\[([^\]]*)\]\(([^)]+)\)'
    for match in re.finditer(md_link_pattern, text):
        placeholder = placeholder_pattern.format(counter)
        temp_replacements[placeholder] = match.group(0)
        text = text.replace(match.group(0), placeholder)
        counter += 1
    
    # URL自動リンク化（IPv6アドレス対応）
    # IPv6アドレスを含むURLに対応
    url_pattern = r'(https?://(?:\[[0-9a-fA-F:]+\]|[^\s<>"\'`\]]+)(?::[0-9]+)?[^\s<>"\'`]*)'
    
    def replace_url(match):
        url = match.group(1)
        # URLの末尾の句読点を除去（ただし、IPv6の角括弧は保持）
        url = re.sub(r'[.,;!?]+$', '', url)
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{url}</a>'
    
    text = re.sub(url_pattern, replace_url, text)
    
    # 保護したリンクを復元
    for placeholder, original in temp_replacements.items():
        text = text.replace(placeholder, original)
    
    return text


def preprocess_single_newlines(text):
    """単一の改行を2つのスペース+改行に変換（Markdownの強制改行）
    ただし、コードブロック内は除外"""
    if not text:
        return ""
    
    # まず改行コードを統一（Windows形式のCRLFをUnix形式のLFに変換）
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    lines = text.split('\n')
    result_lines = []
    in_fenced_code = False
    
    for i, line in enumerate(lines):
        # フェンスコードブロック（```）の検出
        if line.strip().startswith('```'):
            in_fenced_code = not in_fenced_code
            result_lines.append(line)
            continue
        
        # コードブロック内の場合はそのまま追加
        if in_fenced_code:
            result_lines.append(line)
            continue
        
        # 次の行が存在し、現在の行が空でなく、次の行も空でない場合
        if (i + 1 < len(lines) and 
            line.strip() and 
            lines[i + 1].strip() and
            not lines[i + 1].startswith('#') and  # 見出しの前は改行しない
            not line.endswith('  ')):  # 既に強制改行がある場合は除外
            # Markdownの強制改行（行末に2つのスペース）を追加
            result_lines.append(line + '  ')
        else:
            result_lines.append(line)
    
    return '\n'.join(result_lines)


def sanitize_html(html_content):
    """HTMLからセキュリティ上危険なタグと属性を除去"""
    if not html_content:
        return ""
    
    # 危険なタグを除去
    dangerous_tags = [
        'script', 'iframe', 'object', 'embed', 'applet', 
        'form', 'input', 'button', 'textarea', 'select',
        'meta', 'link', 'style', 'base'
    ]
    
    for tag in dangerous_tags:
        # 開始タグと終了タグを除去
        pattern = rf'<\s*{tag}[^>]*>.*?<\s*/\s*{tag}\s*>'
        html_content = re.sub(pattern, '', html_content, flags=re.IGNORECASE | re.DOTALL)
        # 自己終了タグを除去
        pattern = rf'<\s*{tag}[^>]*/?>'
        html_content = re.sub(pattern, '', html_content, flags=re.IGNORECASE)
    
    # 危険な属性を除去
    dangerous_attrs = [
        'onclick', 'onload', 'onerror', 'onmouseover', 'onmouseout',
        'onfocus', 'onblur', 'onchange', 'onsubmit', 'onreset',
        'javascript:', 'vbscript:', 'data:'
    ]
    
    for attr in dangerous_attrs:
        if attr.endswith(':'):
            # プロトコル系の除去
            pattern = rf'{attr}[^"\'\s>]*'
        else:
            # イベントハンドラ系の除去
            pattern = rf'{attr}\s*=\s*["\'][^"\']*["\']'
        html_content = re.sub(pattern, '', html_content, flags=re.IGNORECASE)
    
    return html_content


def markdown_to_html(text):
    """MarkdownテキストをHTMLに変換"""
    if not text:
        return ""
    
    # デバッグ: 入力を確認
    print(f"[DEBUG] markdown_to_html input: {repr(text[:100])}...")
    
    # 1つの改行を2つのスペース+改行に変換（Markdownの強制改行）
    preprocessed_text = preprocess_single_newlines(text)
    
    # デバッグ: 前処理後のテキストを確認
    print(f"[DEBUG] after preprocessing: {repr(preprocessed_text[:100])}...")
    
    # Markdownエクステンションを設定
    md = markdown.Markdown(extensions=[
        'markdown.extensions.fenced_code',  # コードブロック
        'markdown.extensions.tables',       # テーブル
        'markdown.extensions.toc',          # 目次
        'markdown.extensions.codehilite',   # シンタックスハイライト
    ])
    
    # HTMLを生成
    html_content = md.convert(preprocessed_text)
    
    # セキュリティ: 危険なHTMLタグとスクリプトを除去
    html_content = sanitize_html(html_content)
    
    # Markdown変換後にURL自動リンク化を適用
    html_content = auto_link_urls(html_content)
    
    # デバッグ: 出力を確認
    print(f"[DEBUG] markdown_to_html output: {repr(str(html_content)[:100])}...")
    
    return Markup(html_content)


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
    
    # 日本語やその他の文字を適切に処理
    import unicodedata
    
    # Unicode正規化
    title = unicodedata.normalize('NFKC', title)
    
    # 小文字に変換
    slug = title.lower()
    
    # 英数字とハイフン、アンダースコア以外を除去
    slug = re.sub(r'[^\w\s-]', '', slug)
    
    # スペースをハイフンに変換
    slug = re.sub(r'[-\s]+', '-', slug)
    
    # 先頭末尾のハイフンを除去
    slug = slug.strip('-')
    
    return slug


def format_datetime(dt):
    """日時をフォーマット"""
    if not dt:
        return ""
    
    if isinstance(dt, str):
        return dt
    
    return dt.strftime('%Y/%m/%d %H:%M')


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
    'auto_link_urls': auto_link_urls,
}
