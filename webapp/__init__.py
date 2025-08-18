# webapp/__init__.py
import logging

from flask import Flask, request, redirect, url_for, render_template, make_response, flash, g
from datetime import datetime, timezone

from flask_babel import get_locale
from flask_babel import gettext as _

from .extensions import db, migrate, login_manager, babel
from core.db_log_handler import DBLogHandler


def create_app():
    """アプリケーションファクトリ"""
    from dotenv import load_dotenv
    from .config import Config

    # .env を読み込む（環境変数が未設定の場合のみ）
    load_dotenv()

    app = Flask(__name__)
    app.config.from_object(Config)
    app.config.setdefault("LAST_BEAT_AT", None)

    # 拡張初期化
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    babel.init_app(app, locale_selector=_select_locale)

    # ★ Jinja から get_locale() を使えるようにする
    app.jinja_env.globals["get_locale"] = get_locale

    # Logging configuration
    if not any(isinstance(h, DBLogHandler) for h in app.logger.handlers):
        db_handler = DBLogHandler()
        db_handler.setLevel(logging.INFO)
        app.logger.addHandler(db_handler)
    app.logger.setLevel(logging.INFO)



    # モデル import（migrate 用に認識させる）
    from core.models import user as _user  # noqa: F401
    from core.models import google_account as _google_account  # noqa: F401
    from core.models import photo_models as _photo_models    # noqa: F401
    from core.models import job_sync as _job_sync    # noqa: F401
    from core.models import picker_session as _picker_session  # noqa: F401
    from core.models import picker_import_item as _picker_import_item  # noqa: F401
    from core.models import log as _log  # noqa: F401


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

    # エラーハンドラ
    from flask import jsonify
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(Exception)
    def handle_exception(e):
        if isinstance(e, HTTPException):
            code = e.code
            message = e.description
        else:
            code = 500
            message = str(e)

        app.logger.error(
            message,
            exc_info=e,
            extra={
                "path": request.path,
                "method": request.method,
                "remote_addr": request.remote_addr,
                "user_agent": request.user_agent.string,
                "query_string": request.query_string.decode(),
            },
        )
        g.exception_logged = True

        if request.path.startswith("/api"):
            return jsonify({"error": "internal_error", "message": message}), code
        return render_template("error.html", message=message), code

    @app.after_request
    def log_server_error(response):
        if response.status_code >= 500 and not getattr(g, "exception_logged", False):
            app.logger.error(
                f"{response.status_code} {request.path}",
                extra={
                    "path": request.path,
                    "method": request.method,
                    "remote_addr": request.remote_addr,
                    "user_agent": request.user_agent.string,
                    "query_string": request.query_string.decode(),
                },
            )
        return response

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

