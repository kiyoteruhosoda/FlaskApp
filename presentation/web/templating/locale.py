"""リクエストごとの表示ロケール選択.

Flask-Babel の ``locale_selector`` として用いる。選択優先順位は
1) ``lang`` クッキー 2) ``Accept-Language`` ヘッダ 3) 既定ロケール。
リクエストコンテキスト外では既定ロケールを返す。
"""

from __future__ import annotations

from flask import has_request_context, request

from shared.kernel.settings.settings import settings


def select_locale() -> str:
    """1) cookie lang 2) Accept-Language 3) default"""

    if not has_request_context():
        return settings.babel_default_locale or "en"

    cookie_lang = request.cookies.get("lang")
    languages = [lang for lang in settings.languages if lang]
    if cookie_lang in languages:
        return cookie_lang

    best_match = request.accept_languages.best_match(languages) if languages else None
    if best_match:
        return best_match

    return settings.babel_default_locale or "en"
