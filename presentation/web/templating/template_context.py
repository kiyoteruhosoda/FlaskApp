"""テンプレートレンダリング用のコンテキスト供給.

``create_app()`` に定義されていたテンプレート向けの共通コンテキスト設定を集約する。
責務は、リクエストごとの表示タイムゾーン解決、テンプレートへ渡す共通変数
（バージョン・タイムゾーン・言語セレクタ）の供給、および Jinja からの
``get_locale`` 利用の有効化。
"""

from __future__ import annotations

from datetime import timezone

from flask import Flask, g, request
from flask_babel import get_locale
from flask_babel import gettext as _

from core.settings import settings
from core.version import get_version_string

from .timezone import resolve_timezone


def register_template_context(app: Flask) -> None:
    """タイムゾーン解決フックと共通テンプレート変数の供給を登録する。"""

    # ★ Jinja から get_locale() を使えるようにする
    app.jinja_env.globals["get_locale"] = get_locale

    @app.before_request
    def _set_request_timezone():
        tz_cookie = request.cookies.get("tz")
        fallback = settings.babel_default_timezone
        tz_name, tzinfo = resolve_timezone(tz_cookie, fallback)
        g.user_timezone_name = tz_name
        g.user_timezone = tzinfo

    @app.context_processor
    def inject_version():
        languages = [str(lang).strip() for lang in settings.languages if str(lang).strip()]
        if not languages:
            default_language = settings.babel_default_locale or "en"
            if default_language:
                languages = [default_language]

        default_language = settings.babel_default_locale or (
            languages[0] if languages else "en"
        )

        locale_obj = get_locale()
        current_language = str(locale_obj) if locale_obj else default_language
        if "_" in current_language:
            short_lang = current_language.split("_")[0]
            if short_lang in languages:
                current_language = short_lang
        if current_language not in languages and languages:
            current_language = languages[0]

        language_labels = {
            "ja": _("Japanese"),
            "en": _("English"),
        }
        for lang in languages:
            language_labels.setdefault(lang, lang.upper())

        return dict(
            app_version=get_version_string(),
            current_timezone=getattr(g, "user_timezone", timezone.utc),
            current_timezone_name=getattr(g, "user_timezone_name", "UTC"),
            language_selector_languages=languages,
            language_labels=language_labels,
            current_language=current_language,
        )
