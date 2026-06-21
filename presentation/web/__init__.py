# webapp/__init__.py
import importlib
import json
import os
from datetime import timezone

from contextlib import contextmanager

from flask import (
    Flask,
    app,
    g,
    current_app,
    jsonify,
    request,
    session,
)
from flask_login import current_user, logout_user

from flask_babel import get_locale
from flask_babel import gettext as _

from core.settings import settings

from .extensions import db, migrate, login_manager, babel, api as smorest_api
from .error_handlers import register_error_handlers
from webapp.auth import SERVICE_LOGIN_SESSION_KEY, SERVICE_LOGIN_TOKEN_SESSION_KEY
from .timezone import resolve_timezone
from core.settings import settings
from webapp.services.token_service import TokenService
from .cors import configure_cors
from .jinja_filters import register_template_filters
from .persisted_settings import apply_persisted_settings
from .cli_commands import register_cli_commands
from .request_logging import register_request_logging
from .unauthorized_handler import register_unauthorized_handler
from .locale import select_locale
from .system_routes import register_system_routes
from .blueprints import register_blueprints
from .openapi_setup import apply_openapi_config_defaults, register_openapi_runtime
from .logging_setup import configure_logging

# 後方互換: 旧名 ``_apply_persisted_settings`` を広く参照しているため別名を維持する。
_apply_persisted_settings = apply_persisted_settings


def create_app():
    """アプリケーションファクトリ"""
    from dotenv import load_dotenv
    from .config import BaseApplicationSettings
    from werkzeug.middleware.proxy_fix import ProxyFix

    # .env を読み込む（環境変数が未設定の場合のみ）
    load_dotenv()

    from flask.testing import FlaskClient

    class _HostPreservingClient(FlaskClient):
        def __init__(self, *args, **kwargs):  # type: ignore[override]
            super().__init__(*args, **kwargs)
            self.environ_base.setdefault("SERVER_NAME", "localhost")
            self.environ_base.setdefault("HTTP_HOST", "localhost")

        def open(self, *args, **kwargs):  # type: ignore[override]
            if not kwargs.get("base_url"):
                kwargs["base_url"] = "http://localhost"
            return super().open(*args, **kwargs)

        @contextmanager
        def session_transaction(self, *args, **kwargs):  # type: ignore[override]
            kwargs.setdefault("base_url", "http://localhost")
            with super().session_transaction(*args, **kwargs) as sess:
                yield sess

    app = Flask(__name__)
    app.test_client_class = _HostPreservingClient
    app.config.from_object(BaseApplicationSettings)

    # ``BaseApplicationSettings`` はモジュール import 時に ``DATABASE_URI`` を読み取って
    # 凍結する。同一プロセスで複数回 ``create_app()`` を呼ぶ（テスト等）場合でも、
    # 各呼び出しが現在の設定の DB に接続できるよう実行時に再解決する。
    # 本番では import 時と同値のため影響しない。設定値は Settings 経由で取得する。
    runtime_database_uri = settings.database_uri
    if runtime_database_uri:
        app.config["SQLALCHEMY_DATABASE_URI"] = runtime_database_uri
    app.config.setdefault("LAST_BEAT_AT", None)
    apply_openapi_config_defaults(app)

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

    with app.app_context():
        apply_persisted_settings(app)
        database_uri = settings.sqlalchemy_database_uri
        testing_mode = settings.testing

    if testing_mode and isinstance(database_uri, str) and database_uri.startswith("sqlite:///"):
        db_path = database_uri.replace("sqlite:///", "", 1)
        if db_path and db_path != ":memory:":
            try:
                os.remove(db_path)
            except FileNotFoundError:
                pass

    env_overrides = {
        "MEDIA_TEMP_DIRECTORY": settings.tmp_directory_configured,
        "MEDIA_ORIGINALS_DIRECTORY": settings.media_originals_directory,
        "MEDIA_PLAYBACK_DIRECTORY": settings.media_play_directory,
        "MEDIA_THUMBNAILS_DIRECTORY": settings.media_thumbs_directory,
        "MEDIA_LOCAL_IMPORT_DIRECTORY": settings.local_import_directory_configured,
        "MEDIA_DOWNLOAD_SIGNING_KEY": settings.media_download_signing_key,
    }
    for key, value in env_overrides.items():
        if value:
            app.config[key] = value

    babel.init_app(app, locale_selector=select_locale)
    smorest_api.init_app(app)
    
    # Initialize Flask-Mailman
    from .extensions import mail
    # メール機能が有効な場合のみ設定を適用して初期化
    if settings.mail_enabled:
        app.config['MAIL_SERVER'] = settings.mail_server
        app.config['MAIL_PORT'] = settings.mail_port
        app.config['MAIL_USE_TLS'] = settings.mail_use_tls
        app.config['MAIL_USE_SSL'] = settings.mail_use_ssl
        app.config['MAIL_USERNAME'] = settings.mail_username
        app.config['MAIL_PASSWORD'] = settings.mail_password
        app.config['MAIL_DEFAULT_SENDER'] = settings.mail_default_sender or settings.mail_username
        mail_state = mail.init_app(app)
        mail.state = mail_state
        mail.app = app

    register_error_handlers(app)

    # Local Import監査ロガー初期化
    with app.app_context():
        try:
            from bounded_contexts.photonest.infrastructure.local_import.logging_integration import init_audit_logger
            init_audit_logger()
            app.logger.info("Local Import監査ロガーを初期化しました")
        except Exception as e:
            app.logger.warning(f"Local Import監査ロガー初期化をスキップしました: {e}")

    configure_cors(app)
    register_openapi_runtime(app)

    # ★ Jinja から get_locale() を使えるようにする
    app.jinja_env.globals["get_locale"] = get_locale

    # テンプレートコンテキストプロセッサ：バージョン情報とタイムゾーンを追加
    from core.version import get_version_string

    @app.before_request
    def _set_request_timezone():
        tz_cookie = request.cookies.get("tz")
        fallback = settings.babel_default_timezone
        tz_name, tzinfo = resolve_timezone(tz_cookie, fallback)
        g.user_timezone_name = tz_name
        g.user_timezone = tzinfo

    @app.before_request
    def _apply_service_login_scope():
        if not session.get(SERVICE_LOGIN_SESSION_KEY):
            return
        if getattr(g, "current_token_scope", None) is not None:
            return

        token = request.cookies.get("access_token")
        if not token:
            g.current_token_scope = set()
            session.pop(SERVICE_LOGIN_SESSION_KEY, None)
            session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
            logout_user()
            g.service_login_clear_cookie = True
            return

        principal = TokenService.create_principal_from_token(token)
        if not principal:
            g.current_token_scope = set()
            session.pop(SERVICE_LOGIN_SESSION_KEY, None)
            session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
            logout_user()
            g.service_login_clear_cookie = True
            return

        principal_scope = principal.scope if principal else frozenset()
        if current_user.is_authenticated and hasattr(current_user, "get_id"):
            current_id = str(current_user.get_id())
            if current_id != str(principal.get_id()):
                current_app.logger.warning(
                    "Service login token subject mismatch; ignoring token scope",
                    extra={"event": "auth.service_login", "path": request.path},
                )
                logout_user()
                session.pop(SERVICE_LOGIN_SESSION_KEY, None)
                session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
                g.current_token_scope = set()
                g.service_login_clear_cookie = True
                return

        if principal.is_service_account:
            session[SERVICE_LOGIN_TOKEN_SESSION_KEY] = token
        g.current_token_scope = set(principal_scope)

    @app.after_request
    def _clear_service_login_cookie(response):
        if getattr(g, "service_login_clear_cookie", False):
            response.delete_cookie("access_token")
        return response

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

    register_template_filters(app)

    disable_db_logging = testing_mode or settings.testing
    configure_logging(app, database_uri=database_uri, disable_db_logging=disable_db_logging)



    # モデル import（migrate 用に認識させる）
    from core.models import user as _user  # noqa: F401
    from core.models import google_account as _google_account  # noqa: F401
    from core.models import photo_models as _photo_models    # noqa: F401
    from core.models import job_sync as _job_sync    # noqa: F401
    from core.models import picker_session as _picker_session  # noqa: F401
    from core.models import picker_import_task as _picker_import_task  # noqa: F401
    from core.models import log as _log  # noqa: F401
    from core.models.wiki import models as _wiki_models  # noqa: F401
    from core.models import totp as _totp_models  # noqa: F401
    from bounded_contexts.certs.infrastructure import models as _cert_models  # noqa: F401


    # Blueprint 登録
    register_blueprints(app, testing_mode=testing_mode)

    # CLI コマンド登録
    register_cli_commands(app)

    # React アプリケーション用ルート登録（最後に登録してcatch-allが他のルートと競合しないようにする）
    from .react_routes import register_react_routes
    register_react_routes(app)

    # カスタムエラーハンドラーを追加（デバッグ強化）
    @app.errorhandler(422)
    def handle_validation_error(e):
        """Marshmallow validation errors (422 Unprocessable Entity) のデバッグ強化"""
        import traceback
        from marshmallow import ValidationError
        from flask_smorest.error_handler import ErrorHandlerMixin
        
        app.logger.error(f"422 Validation Error occurred:")
        app.logger.error(f"Request path: {request.path}")
        app.logger.error(f"Request method: {request.method}")
        app.logger.error(f"Request headers: {dict(request.headers)}")
        app.logger.error(f"Request args: {request.args.to_dict()}")
        
        try:
            request_json = request.get_json(force=True)
            app.logger.error(f"Request JSON: {request_json}")
        except Exception as json_error:
            app.logger.error(f"Failed to parse request JSON: {json_error}")
            app.logger.error(f"Raw request data: {request.data}")
        
        app.logger.error(f"Exception details: {e}")
        app.logger.error(f"Exception type: {type(e)}")
        if hasattr(e, 'description'):
            app.logger.error(f"Exception description: {e.description}")
        if hasattr(e, 'data'):
            app.logger.error(f"Exception data: {e.data}")
            
        # Traceback も出力
        app.logger.error(f"Traceback:\n{traceback.format_exc()}")
        
        # デフォルトのFlask-Smorest処理に委任
        return {"error": "validation_failed", "message": str(e), "details": getattr(e, 'data', {})}, 422

    @app.errorhandler(500)
    def handle_internal_server_error(e):
        """500 Internal Server Error を1件の構造化ログとして記録する。

        元例外のメッセージ・リクエストパス・トレースバックを単一の Log
        エントリにまとめる。Flask 既定の例外ログ（log_exception）は下で
        抑制しているため、500 についてはこのハンドラが唯一の記録元となる。
        """
        original = getattr(e, "original_exception", None)
        exc = original if original is not None else e

        # api.server_error の after_request ログと二重化しないよう印を付ける
        g.exception_logged = True

        app.logger.error(
            json.dumps({"message": str(exc), "status": 500}, ensure_ascii=False),
            exc_info=True,
            extra={
                "event": "api.server_error",
                "path": request.path,
                "request_id": getattr(g, "request_id", None),
            },
        )

        # メッセージをロケールに合わせて翻訳し、Content-Language を付与する
        locale = str(get_locale() or app.config.get("BABEL_DEFAULT_LOCALE", "en"))
        response = jsonify(
            {"error": "internal_server_error", "message": _("Internal Server Error")}
        )
        response.status_code = 500
        response.headers["Content-Language"] = locale
        return response

    def _log_exception_via_handler(exc_info):
        """Flask 既定の例外ログを抑制する。

        500 は handle_internal_server_error が構造化ログとして記録するため、
        Flask が出力する "Exception on ..." の重複ログを抑える。
        """
        return None

    app.log_exception = _log_exception_via_handler

    @app.before_request
    def _apply_login_disabled_for_testing():
        if settings.testing:
            app.config['LOGIN_DISABLED'] = True

    register_request_logging(app)

    # 注意：既存のルートは削除し、Reactアプリケーションが処理します
    # ルート "/" は react_routes.py で処理される

    register_unauthorized_handler(app, login_manager)
    register_system_routes(app)

    with app.app_context():
        db_uri = settings.sqlalchemy_database_uri or ""
        if isinstance(db_uri, str) and db_uri.startswith("sqlite://"):
            db.create_all()

    return app


def __getattr__(name: str):
    if name == "api":
        module = importlib.import_module("webapp.api")
        globals()[name] = module
        return module
    if name == "auth":
        module = importlib.import_module("webapp.auth")
        globals()[name] = module
        return module
    raise AttributeError(f"module 'webapp' has no attribute {name!r}")

