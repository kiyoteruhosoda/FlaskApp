# webapp/__init__.py
import importlib
import os

from flask import Flask

from core.settings import settings

from .extensions import db, migrate, login_manager, babel, api as smorest_api
from .error_handlers import register_error_handlers, register_debug_error_handlers
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
from .service_login import register_service_login_hooks
from .template_context import register_template_context
from .test_client import HostPreservingClient
from .proxy_fix import apply_debug_proxy_fix
from .mail_setup import configure_mail

# 後方互換: 旧名 ``_apply_persisted_settings`` を広く参照しているため別名を維持する。
_apply_persisted_settings = apply_persisted_settings


def create_app():
    """アプリケーションファクトリ"""
    from dotenv import load_dotenv
    from .config import BaseApplicationSettings

    # .env を読み込む（環境変数が未設定の場合のみ）
    load_dotenv()

    app = Flask(__name__)
    app.test_client_class = HostPreservingClient
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
    apply_debug_proxy_fix(app)

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

    configure_mail(app)

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

    register_template_context(app)
    register_service_login_hooks(app)
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
    register_debug_error_handlers(app)

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
        module = importlib.import_module("presentation.web.api")
        globals()[name] = module
        return module
    if name == "auth":
        module = importlib.import_module("presentation.web.auth")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

