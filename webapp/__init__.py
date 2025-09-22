# webapp/__init__.py
import logging
import json

import time
from uuid import uuid4

from flask import Flask, app, request, redirect, url_for, render_template, make_response, flash, jsonify, g
from datetime import datetime, timezone

from flask_babel import get_locale
from flask_babel import gettext as _

from .extensions import db, migrate, login_manager, babel
from .timezone import resolve_timezone, convert_to_timezone
from core.db_log_handler import DBLogHandler

# エラーハンドラ
from werkzeug.exceptions import HTTPException


def create_app():
    """アプリケーションファクトリ"""
    from dotenv import load_dotenv
    from .config import Config
    from werkzeug.middleware.proxy_fix import ProxyFix

    # .env を読み込む（環境変数が未設定の場合のみ）
    load_dotenv()

    app = Flask(__name__)
    app.config.from_object(Config)
    app.config.setdefault("LAST_BEAT_AT", None)
    
    # リバースプロキシ（nginx等）使用時のHTTPS検出
    # ProxyFixをカスタマイズしてデバッグ情報を追加
    from werkzeug.middleware.proxy_fix import ProxyFix
    
    class DebugProxyFix(ProxyFix):
        def __call__(self, environ, start_response):
            app.logger.debug(f"ProxyFix - Original scheme: {environ.get('wsgi.url_scheme')}")
            app.logger.debug(f"ProxyFix - X-Forwarded-Proto: {environ.get('HTTP_X_FORWARDED_PROTO')}")
            app.logger.debug(f"ProxyFix - X-Forwarded-Host: {environ.get('HTTP_X_FORWARDED_HOST')}")
            result = super().__call__(environ, start_response)
            app.logger.debug(f"ProxyFix - Final scheme: {environ.get('wsgi.url_scheme')}")
            return result
    
    app.wsgi_app = DebugProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # 拡張初期化
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    babel.init_app(app, locale_selector=_select_locale)

    # ★ Jinja から get_locale() を使えるようにする
    app.jinja_env.globals["get_locale"] = get_locale

    # テンプレートコンテキストプロセッサ：バージョン情報とタイムゾーンを追加
    from core.version import get_version_string

    @app.before_request
    def _set_request_timezone():
        tz_cookie = request.cookies.get("tz")
        fallback = app.config.get("BABEL_DEFAULT_TIMEZONE", "UTC")
        tz_name, tzinfo = resolve_timezone(tz_cookie, fallback)
        g.user_timezone_name = tz_name
        g.user_timezone = tzinfo

    @app.context_processor
    def inject_version():
        return dict(
            app_version=get_version_string(),
            current_timezone=getattr(g, "user_timezone", timezone.utc),
            current_timezone_name=getattr(g, "user_timezone_name", "UTC"),
        )

    @app.template_filter("localtime")
    def _localtime_filter(value, fmt="%Y/%m/%d %H:%M"):
        """Render *value* in the user's preferred time zone."""

        if value is None:
            return ""
        if not isinstance(value, datetime):
            return value

        tzinfo = getattr(g, "user_timezone", timezone.utc)
        localized = convert_to_timezone(value, tzinfo)
        if localized is None:
            return ""
        if fmt is None:
            return localized
        return localized.strftime(fmt)

    # Logging configuration
    if not any(isinstance(h, DBLogHandler) for h in app.logger.handlers):
        db_handler = DBLogHandler(app=app)
        db_handler.setLevel(logging.INFO)
        app.logger.addHandler(db_handler)
    
    # デバッグモードでは詳細ログを有効化
    if app.debug:
        app.logger.setLevel(logging.DEBUG)
        # コンソールハンドラーも追加
        import sys
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        app.logger.addHandler(console_handler)
    else:
        app.logger.setLevel(logging.INFO)



    # モデル import（migrate 用に認識させる）
    from core.models import user as _user  # noqa: F401
    from core.models import google_account as _google_account  # noqa: F401
    from core.models import photo_models as _photo_models    # noqa: F401
    from core.models import job_sync as _job_sync    # noqa: F401
    from core.models import picker_session as _picker_session  # noqa: F401
    from core.models import picker_import_task as _picker_import_task  # noqa: F401
    from core.models import log as _log  # noqa: F401
    from core.models.wiki import models as _wiki_models  # noqa: F401


    # Blueprint 登録
    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")
    from .auth.routes import picker as picker_view
    app.add_url_rule("/picker/<int:account_id>", view_func=picker_view, endpoint="picker")

    from .feature_x import bp as feature_x_bp
    app.register_blueprint(feature_x_bp, url_prefix="/feature-x")

    from .admin.routes import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from .photo_view import bp as photo_view_bp
    app.register_blueprint(photo_view_bp, url_prefix="/photo-view")

    from .api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix="/api")

    # 認証なしの健康チェック用Blueprint
    from .health import health_bp
    app.register_blueprint(health_bp, url_prefix="/health")

    # デバッグ用Blueprint（開発環境のみ）
    if app.debug or app.config.get('TESTING'):
        from .debug_routes import debug_bp
        app.register_blueprint(debug_bp, url_prefix="/debug")

    from .wiki import bp as wiki_bp
    app.register_blueprint(wiki_bp, url_prefix="/wiki")

    # CLI コマンド登録
    register_cli_commands(app)

    @app.before_request
    def _apply_login_disabled_for_testing():
        if app.config.get("TESTING"):
            app.config['LOGIN_DISABLED'] = True

    @app.before_request
    def start_timer():
        g.start_time = time.perf_counter()

    @app.before_request
    def log_api_request():
        if request.path.startswith("/api"):
            req_id = str(uuid4())
            g.request_id = req_id
            # Inputログ
            try:
                input_json = request.get_json(silent=True)
            except Exception:
                input_json = None

            log_dict = {
                "method": request.method,
            }
            args_dict = request.args.to_dict()
            if args_dict:
                log_dict["args"] = args_dict
            form_dict = request.form.to_dict()
            if form_dict:
                log_dict["form"] = form_dict
            if input_json:
                log_dict["json"] = input_json
            app.logger.info(
                json.dumps(log_dict, ensure_ascii=False),
                extra={
                    "event": "api.input",
                    "request_id": req_id,
                    "path": request.path,
                }
            )

    @app.after_request
    def log_api_response(response):
        if request.path.startswith("/api"):
            req_id = getattr(g, "request_id", None)
            resp_json = None
            if response.mimetype == "application/json":
                try:
                    resp_json = response.get_json()
                except Exception as e:
                    print(f"Error parsing JSON response {request.path}:", e)
                    resp_json = None
            # Outputログ
            app.logger.info(
                json.dumps({
                    "status": response.status_code,
                    "json": resp_json,
                }, ensure_ascii=False),
                extra={
                    "event": "api.output",
                    "request_id": req_id,
                    "path": request.path,
                }
            )
        return response

    # 404だけ個別に（テンプレでもJSONでも可）
    @app.errorhandler(404)
    def handle_404(e):
        app.logger.info("404 path=%s full=%s ua=%s",
                        request.path, request.full_path, request.user_agent)
        # return render_template("404.html"), 404
        return jsonify(error="Not Found"), 404

    @app.errorhandler(Exception)
    def handle_exception(e):
        is_http = isinstance(e, HTTPException)
        code = e.code if is_http else 500
        # 外部公開メッセージ：5xxは伏せる（内部情報漏えい対策）
        public_message = e.description if (is_http and code < 500) else "Internal Server Error"

        # ログ用の詳細（必要に応じてマスキング）
        try:
            input_json = request.get_json(silent=True)
        except Exception:
            input_json = None

        log_dict = {
            "method": request.method,
            "path": request.path,
            "full_path": request.full_path,
            "ua": request.user_agent.string,
            "status": code,
        }
        qs = request.query_string.decode()
        if qs:
            log_dict["query_string"] = qs

        form_dict = request.form.to_dict()
        if form_dict:
            # ここで鍵っぽいキーはマスク推奨（例）
            for k in list(form_dict.keys()):
                if k.lower() in {"password", "secret", "token"}:
                    form_dict[k] = "***"
            log_dict["form"] = form_dict

        if input_json:
            # JSON もマスク推奨
            scrubbed = dict(input_json)
            for k in list(scrubbed.keys()):
                if k.lower() in {"password", "secret", "token"}:
                    scrubbed[k] = "***"
            log_dict["json"] = scrubbed

        # ★ ログ出力方針：4xxはstackなし、5xxはstack付き
        if is_http and 400 <= code < 500:
            app.logger.warning(json.dumps(log_dict, ensure_ascii=False),
                            extra={"event": "api.http_4xx", "request_id": getattr(g, "request_id", None)})
        else:
            # 5xxのみ stacktrace
            app.logger.exception(json.dumps(log_dict, ensure_ascii=False),
                                extra={"event": "api.http_5xx", "request_id": getattr(g, "request_id", None)})

        g.exception_logged = True

        # レスポンス
        if request.path.startswith("/api"):
            # 5xxの詳細messageは返さない（public_messageに統一）
            return jsonify({"error": "error", "message": public_message}), code

        # HTML（5xxはgenericに）
        return render_template("error.html", message=public_message), code

    @app.after_request
    def log_server_error(response):
        if response.status_code >= 500 and not getattr(g, "exception_logged", False):
            try:
                input_json = request.get_json(silent=True)
            except Exception:
                input_json = None
            log_dict = {
                "status": response.status_code,
                "method": request.method,
                "user_agent": request.user_agent.string,
            }
            qs = request.query_string.decode()
            if qs:
                log_dict["query_string"] = qs
            form_dict = request.form.to_dict()
            if form_dict:
                log_dict["form"] = form_dict
            if input_json:
                log_dict["json"] = input_json
            app.logger.error(
                json.dumps(log_dict, ensure_ascii=False),
                extra={
                    "event": "api.server_error",
                    "path": request.url,
                    "request_id": getattr(g, "request_id", None),
                },
            )
        return response

    @app.after_request
    def add_server_timing(response):
        start = getattr(g, "start_time", None)
        if start is not None:
            duration = (time.perf_counter() - start) * 1000
            response.headers["Server-Timing"] = f"app;dur={duration:.2f}"
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

    @app.route("/.well-known/appspecific/com.chrome.devtools.json")
    def chrome_devtools_json():
        return {}, 204  # 空レスポンスを返す

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if db_uri.startswith("sqlite://"):
        with app.app_context():
            db.create_all()

    return app


def _select_locale():
    """1) cookie lang 2) Accept-Language 3) default"""
    from flask import current_app

    cookie_lang = request.cookies.get("lang")
    if cookie_lang in current_app.config["LANGUAGES"]:
        return cookie_lang
    return request.accept_languages.best_match(current_app.config["LANGUAGES"])


def register_cli_commands(app):
    """CLI コマンドを登録"""
    import click
    from datetime import datetime, timezone
    from core.models.user import User, Role, Permission

    @app.cli.command("version")
    def show_version():
        """アプリケーションのバージョン情報を表示"""
        from core.version import get_version_info, get_version_string
        
        click.echo("=== PhotoNest Version Information ===")
        version_info = get_version_info()
        
        click.echo(f"Version: {get_version_string()}")
        click.echo(f"Commit Hash: {version_info['commit_hash']}")
        click.echo(f"Branch: {version_info['branch']}")
        click.echo(f"Commit Date: {version_info['commit_date']}")
        click.echo(f"Build Date: {version_info['build_date']}")

    @app.cli.command("seed-master")
    @click.option('--force', is_flag=True, help='既存データがあっても強制実行')
    def seed_master_data(force):
        """マスタデータを投入"""
        from scripts.seed_master_data import (
            seed_roles, seed_permissions, seed_role_permissions, seed_admin_user
        )
        
        click.echo("=== PhotoNest Master Data Seeding ===")
        
        # 既存データチェック
        if not force:
            if Role.query.first() or Permission.query.first():
                click.echo("Warning: Master data already exists. Use --force to override.")
                return
        
        try:
            click.echo("\n1. Seeding roles...")
            seed_roles()
            
            click.echo("\n2. Seeding permissions...")
            seed_permissions()
            
            db.session.commit()
            
            click.echo("\n3. Seeding role-permission relationships...")
            seed_role_permissions()
            
            click.echo("\n4. Seeding admin user...")
            seed_admin_user()
            
            db.session.commit()
            click.echo("\n=== Seeding completed successfully! ===")
            
        except Exception as e:
            db.session.rollback()
            click.echo(f"\n=== Seeding failed: {e} ===", err=True)
            raise click.ClickException(str(e))

