"""アプリ直下のシステム・ユーティリティルート.

``create_app()`` にインライン定義されていた小規模ルート（言語切替・i18n 診断・
Chrome DevTools 応答・セッションテストページ）を集約する。テンプレートが
``url_for('set_lang')`` のようにグローバルなエンドポイント名を参照するため、
Blueprint 化せず ``app`` へ直接登録してエンドポイント名を維持する。
"""

from __future__ import annotations

from flask import Flask, make_response, redirect, render_template, request, url_for
from flask_babel import gettext as _

from presentation.web.templating.locale import select_locale


def register_system_routes(app: Flask) -> None:
    """言語切替・i18n 診断などのユーティリティルートを登録する。"""

    # テストページ（デバッグ用）
    @app.route("/test/session-refresh")
    def test_session_refresh():
        return render_template("test_session_refresh.html")

    # 言語切替（/lang/ja, /lang/en）
    @app.get("/lang/<lang_code>")
    def set_lang(lang_code):
        if lang_code not in app.config["LANGUAGES"]:
            lang_code = app.config["BABEL_DEFAULT_LOCALE"]
        resp = make_response(redirect(request.headers.get("Referer", url_for("index"))))
        # 30日保持
        resp.set_cookie(
            "lang",
            lang_code,
            max_age=60 * 60 * 24 * 30,
            httponly=False,
            path="/",
        )
        return resp

    @app.get("/i18n-probe")
    def i18n_probe():
        return {
            "cookie": request.cookies.get("lang"),
            "locale": str(select_locale()),
            "t_Login": _("Login"),
            "t_Home": _("Home"),
            "t_LoginMessage": _("Please log in to access this page."),
        }

    @app.route("/.well-known/appspecific/com.chrome.devtools.json")
    def chrome_devtools_json():
        return {}, 204  # 空レスポンスを返す
