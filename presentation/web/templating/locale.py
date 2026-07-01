"""リクエストごとの表示ロケール選択.

Flask-Babel の ``locale_selector`` として用いる。選択優先順位は
1) ``?lang=`` クエリパラメータ 2) ``lang`` クッキー 3) ``Accept-Language``
ヘッダ 4) 既定ロケール（英語）。ログイン前のページでもクエリ/Cookie で
明示的に日英を切り替えられるようにするため、これらをブラウザの
``Accept-Language`` より優先する。
リクエストコンテキスト外では既定ロケールを返す。
"""

from __future__ import annotations

from flask import has_request_context, request

from shared.kernel.settings.settings import settings


def select_locale() -> str:
    """1) query ?lang= 2) cookie lang 3) Accept-Language 4) default（英語）"""

    if not has_request_context():
        return settings.babel_default_locale or "en"

    languages = [lang for lang in settings.languages if lang]

    query_lang = request.args.get("lang")
    if query_lang in languages:
        return query_lang

    cookie_lang = request.cookies.get("lang")
    if cookie_lang in languages:
        return cookie_lang

    best_match = request.accept_languages.best_match(languages) if languages else None
    if best_match:
        return best_match

    return settings.babel_default_locale or "en"
