# webapp/__init__.py
import os
from flask import Flask, request, redirect, url_for, render_template, make_response, flash
from dotenv import load_dotenv
from datetime import datetime, timezone

# .env を最初に読む（これより後の import で環境変数が使える）
load_dotenv()

from .extensions import db, migrate, login_manager, babel
from .config import Config
from flask_babel import get_locale
from flask_babel import gettext as _

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 拡張初期化
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    babel.init_app(app, locale_selector=_select_locale)

    # ★ Jinja から get_locale() を使えるようにする
    app.jinja_env.globals["get_locale"] = get_locale



    # モデル import（migrate 用に認識させる）
    from .models import user as _user  # noqa: F401
    from .models import google_account as _google_account  # noqa: F401
    from .models import photo_models as _photo_models    # noqa: F401


    # Blueprint 登録
    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")

    from .feature_x import bp as feature_x_bp
    app.register_blueprint(feature_x_bp, url_prefix="/feature-x")

    from .admin.routes import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from .photo_view import bp as photo_view_bp
    app.register_blueprint(photo_view_bp, url_prefix="/photo-view")

    from .api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.after_request
    def add_time_header(response):
        response.headers["X-Server-Time"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return response

    # ルート
    @app.route("/")
    def index():
        # HTML レスポンスを生成
        return make_response(render_template("index.html"))

    # 言語切替（/lang/ja, /lang/en）
    @app.get("/lang/<lang_code>")
    def set_lang(lang_code):
        if lang_code not in app.config["LANGUAGES"]:
            lang_code = app.config["BABEL_DEFAULT_LOCALE"]
        resp = make_response(redirect(request.headers.get("Referer", url_for("index"))))
        # 30日保持
        resp.set_cookie("lang", lang_code, max_age=60 * 60 * 24 * 30, httponly=False)
        return resp
    
    @login_manager.unauthorized_handler
    def unauthorized():
        # i18nメッセージを自分で出す（カテゴリも自由）
        flash(_("Please log in to access this page."), "error")
        # 元のURLへ戻れるよう next を付ける
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for("auth.login", next=next_url))

    @app.get("/i18n-probe")
    def i18n_probe():
        return {
            "cookie": request.cookies.get("lang"),
            "locale": str(_select_locale()),
            "t_Login": _("Login"),
            "t_Home": _("Home"),
            "t_LoginMessage": _("Please log in to access this page."),
        }

    return app


def _select_locale():
    """1) cookie lang 2) Accept-Language 3) default"""
    from flask import current_app

    cookie_lang = request.cookies.get("lang")
    if cookie_lang in current_app.config["LANGUAGES"]:
        return cookie_lang
    return request.accept_languages.best_match(current_app.config["LANGUAGES"])

