# presentation/web/__init__.py
import importlib
import os

from flask import Flask

from shared.kernel.settings.settings import settings

from .bootstrap.extensions import db, migrate, login_manager, babel, api as smorest_api
from .middleware.error_handlers import register_error_handlers, register_debug_error_handlers
from .bootstrap.cors import configure_cors
from .bootstrap.persisted_settings import (
    apply_persisted_settings,
    refresh_persisted_settings_if_stale,
)
from .bootstrap.cli_commands import register_cli_commands
from .middleware.request_logging import register_request_logging
from .middleware.unauthorized_handler import register_unauthorized_handler
from .templating.locale import select_locale
from .routes.system_routes import register_system_routes
from .blueprints import register_blueprints
from .openapi.setup import apply_openapi_config_defaults, register_openapi_runtime
from .bootstrap.logging_setup import configure_logging
from .routes.service_login import register_service_login_hooks
from .bootstrap.test_client import HostPreservingClient
from .bootstrap.proxy_fix import apply_debug_proxy_fix
from .bootstrap.mail_setup import configure_mail

# 後方互換: 旧名 ``_apply_persisted_settings`` を広く参照しているため別名を維持する。
_apply_persisted_settings = apply_persisted_settings


def create_app():
    """アプリケーションファクトリ"""
    from dotenv import load_dotenv
    from .bootstrap.config import BaseApplicationSettings

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

    # モデル import（migrate 用に認識させる、かつマッパー設定前にすべてのモデルを
    # 登録しておくことで SQLAlchemy の relationship 文字列解決を保証する）
    import shared.infrastructure.models.user as _user  # noqa: F401
    import shared.infrastructure.models.passkey as _passkey  # noqa: F401
    import shared.infrastructure.models.google_account as _google_account  # noqa: F401
    import shared.infrastructure.models.service_account as _service_account  # noqa: F401
    import shared.infrastructure.models.service_account_api_key as _service_account_api_key  # noqa: F401
    import shared.infrastructure.models.password_reset_token as _password_reset_token  # noqa: F401
    import bounded_contexts.photonest.infrastructure.photo_models as _photo_models  # noqa: F401
    import shared.infrastructure.models.job_sync as _job_sync  # noqa: F401
    import bounded_contexts.picker_import.infrastructure.picker_session as _picker_session  # noqa: F401
    import bounded_contexts.picker_import.infrastructure.picker_import_task as _picker_import_task  # noqa: F401
    import shared.infrastructure.models.log as _log  # noqa: F401
    import shared.infrastructure.models.worker_log as _worker_log  # noqa: F401
    import shared.infrastructure.models.celery_task as _celery_task  # noqa: F401
    import shared.infrastructure.models.system_setting as _system_setting  # noqa: F401
    import bounded_contexts.wiki.infrastructure.wiki_models as _wiki_models  # noqa: F401
    import bounded_contexts.totp.infrastructure.totp_models as _totp_models  # noqa: F401
    from bounded_contexts.certs.infrastructure import models as _cert_models  # noqa: F401

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

    register_service_login_hooks(app)

    disable_db_logging = testing_mode or settings.testing
    configure_logging(app, database_uri=database_uri, disable_db_logging=disable_db_logging)



    # Blueprint 登録
    register_blueprints(app, testing_mode=testing_mode)

    # CLI コマンド登録
    register_cli_commands(app)

    # React アプリケーション用ルート登録（最後に登録してcatch-allが他のルートと競合しないようにする）
    from .routes.react_routes import register_react_routes
    register_react_routes(app)

    # カスタムエラーハンドラーを追加（デバッグ強化）
    register_debug_error_handlers(app)

    @app.before_request
    def _apply_login_disabled_for_testing():
        if settings.testing:
            app.config['LOGIN_DISABLED'] = True

    # 複数ワーカー構成での設定ドリフト対策:
    # DB の system_settings が更新されていたら app.config へ再適用する
    # （チェックは最大10秒に1回の軽量クエリ）。
    @app.before_request
    def _refresh_persisted_settings():
        refresh_persisted_settings_if_stale(app)

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

