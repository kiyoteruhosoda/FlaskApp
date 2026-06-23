import os
import sys
from pathlib import Path

import pytest

from shared.kernel.settings.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_CORS_SETTINGS,
)

os.environ.setdefault("TESTING", "true")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))


_BOOL_TRUE = {"1", "true", "yes", "on"}


def _coerce_env_value(key: str, default):
    raw = os.environ.get(key)
    if raw is None:
        return default
    if isinstance(default, bool):
        return raw.strip().lower() in _BOOL_TRUE
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(raw)
        except ValueError:
            return default
    if isinstance(default, float):
        try:
            return float(raw)
        except ValueError:
            return default
    if isinstance(default, (list, tuple)):
        return [segment.strip() for segment in raw.split(",") if segment.strip()]
    return raw


@pytest.fixture(autouse=True)
def _restore_os_environ():
    """各テストの前後で ``os.environ`` をスナップショット・復元する.

    多くのテストが ``os.environ`` を書き換えるが後始末をしないため、設定値
    （``DATABASE_URI`` 等）が後続テストへ漏れて連鎖失敗していた。設定は
    ``settings`` シングルトンや ``create_app`` が実行時に環境変数を参照するため、
    テスト境界での環境変数の隔離がグローバルな安定性に直結する。
    """
    import importlib
    import logging as _logging

    snapshot = dict(os.environ)
    try:
        yield
    finally:
        # 追加・変更されたキーを元に戻し、削除されたキーを復元する。
        for key in list(os.environ.keys()):
            if key not in snapshot:
                del os.environ[key]
        for key, value in snapshot.items():
            if os.environ.get(key) != value:
                os.environ[key] = value

        # 環境変数を復元した「後」で webapp.config を正規化する。
        # 一部フィクスチャは test 用環境変数の下で webapp.config を reload するが
        # 元に戻さないため、BaseApplicationSettings の値（SECRET_KEY/DATABASE_URI 等）
        # が後続テストへ漏れて連鎖失敗していた。
        config_module = sys.modules.get("presentation.web.bootstrap.config")
        if config_module is not None:
            try:
                importlib.reload(config_module)
            except Exception:
                pass

        # Flask の app.logger は import 名で共有されるため、DB ログ検証テストが
        # 残した DBLogHandler が累積してログ件数検証を壊す。漏れた分を除去する。
        try:
            from shared.kernel.logging.db_log_handler import DBLogHandler

            _loggers = [_logging.getLogger()]
            _loggers.extend(
                obj
                for obj in _logging.Logger.manager.loggerDict.values()
                if isinstance(obj, _logging.Logger)
            )
            for _logger in _loggers:
                for _handler in list(getattr(_logger, "handlers", [])):
                    if isinstance(_handler, DBLogHandler):
                        _logger.removeHandler(_handler)
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _reset_login_cache_per_request(request):
    """pytest-flask の app context リークによる認証キャッシュの持ち越しを中和する.

    ``pytest-flask`` の autouse fixture ``_push_request_context`` はテスト実行中
    ずっと ``app.test_request_context()`` を push し続ける。Flask は同一アプリの
    app context が既に存在するとそれを再利用するため、テストクライアントの各
    リクエスト間で ``g`` と SQLAlchemy の identity map が共有されてしまう。

    その結果、``flask_login`` が ``g._login_user`` にキャッシュした principal や、
    別 app context でコミットされた DB 変更が後続リクエストへ反映されず、本番では
    起きない（本番はリクエストごとに fresh な app context）テスト固有の不整合が
    生じる。各リクエスト開始時にこれらのキャッシュをクリアし、本番と同様に毎回
    ユーザーを読み直すようにする。
    """

    app = None
    if "app" in request.fixturenames:
        try:
            app = request.getfixturevalue("app")
        except Exception:  # pragma: no cover - app fixture の取得失敗時は何もしない
            app = None

    if app is not None and not getattr(app, "_login_cache_reset_hook", False):
        from flask import g
        from shared.kernel.database.db import db as _db

        def _clear_leaked_request_caches():  # pragma: no cover - テスト環境専用フック
            # flask_login が前リクエストでキャッシュした principal を破棄して再読込させる。
            g.pop("_login_user", None)
            # アプリ独自の per-request キャッシュも破棄する。
            g.pop("current_user", None)
            g.pop("current_user_model", None)
            g.pop("current_principal", None)
            # 別 app context でコミットされた変更を見えるよう identity map を失効させる。
            try:
                _db.session.expire_all()
            except Exception:
                pass

        # ``app.before_request`` は最初のリクエスト後に登録不可となる
        # （module/session スコープで共有される app fixture では既に処理済みの
        # ことがある）。``before_request_funcs`` へ直接追加してロックを回避し、
        # 同一 app へ二重登録しないようフラグで防ぐ。
        app.before_request_funcs.setdefault(None, []).append(
            _clear_leaked_request_caches
        )
        app._login_cache_reset_hook = True

    yield


@pytest.fixture
def app_context():
    """アプリケーションコンテキストを提供するfixture"""
    import os
    import importlib

    # テスト用の環境変数を設定
    original_env = {}
    test_env = {
        "DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "ACCESS_TOKEN_ISSUER": "test-issuer",
        "ACCESS_TOKEN_AUDIENCE": "test-audience",
    }
    
    for key, value in test_env.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value
    
    try:
        # configモジュールをリロード
        import presentation.web.bootstrap.config as config_module
        importlib.reload(config_module)

        from presentation.web import create_app
        from .config import TestConfig
        from presentation.web.bootstrap.extensions import db
        from presentation.web.services.system_setting_service import SystemSettingService
        from presentation.web import _apply_persisted_settings

        app = create_app()
        app.config.from_object(TestConfig)

        with app.app_context():
            db.create_all()
            payload = dict(DEFAULT_APPLICATION_SETTINGS)
            for key in payload.keys():
                if key in app.config:
                    payload[key] = app.config[key]
                payload[key] = _coerce_env_value(key, payload[key])
            SystemSettingService.upsert_application_config(payload)

            cors_raw = os.environ.get("CORS_ALLOWED_ORIGINS")
            if cors_raw:
                allowed_origins = [segment.strip() for segment in cors_raw.split(",") if segment.strip()]
            else:
                allowed_origins = list(
                    app.config.get("CORS_ALLOWED_ORIGINS", DEFAULT_CORS_SETTINGS.get("allowedOrigins", []))
                )
            SystemSettingService.upsert_cors_config(allowed_origins)

            _apply_persisted_settings(app)
            yield app
            db.session.remove()
            db.drop_all()
    finally:
        # 環境変数を元に戻す
        for key, original_value in original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value


SKIP_RULES = [
    ("test_celery_logging.py", "CeleryバックエンドとRedisが必要な結合テストのためスキップ"),
    ("tests/test_celery_", "CeleryワーカーやRedisが必要なためスキップ"),
    ("tests/test_picker_", "Google Photos連携やCeleryワーカーが必要なためスキップ"),
    ("tests/test_local_import", "ローカルインポート用のNASディレクトリ・バックグラウンドサービスが必要なためスキップ"),
    ("tests/test_thumbnail_import.py", "オリジナル写真格納先へのアクセスが必要なためスキップ"),
    ("tests/test_video_transcoding.py", "動画トランスコード用のFFmpeg等外部依存が必要なためスキップ"),
    ("tests/test_backup_cleanup_tasks.py", "バックアップCeleryタスク用のジョブ環境が必要なためスキップ"),
    ("tests/test_logging.py", "本番相当のログテーブルとCelery構成が必要なためスキップ"),
    ("tests/test_api_refresh_token.py", "Google OAuth資格情報が必要なためスキップ"),
    ("test_production_oauth.py", "本番向けOAuth設定とProxy環境が必要なためスキップ"),
    ("tests/test_pagination_fix.py", "実サービスのDB・Pickerデータが必要なためスキップ"),
    ("tests/test_version_admin.py", "管理画面でのバージョン情報エンドポイント依存のためスキップ"),
    ("tests/test_photo_picker.py", "Google Photos Pickerスコープ設定が本番環境依存のためスキップ"),
    ("tests/wiki/", "Wikiサービスのシードデータと全文検索インデックスが必要なためスキップ"),
]

# 外部依存のスキップ対象から除外するテストファイル（相対パス）
ALWAYS_RUN = {
    "tests/test_picker_session_service_local_import.py",
    "tests/test_local_import_duplicate_refresh.py",
    "tests/test_local_import.py",
    "tests/test_local_import_ui.py",
    "tests/test_local_import_services.py",
    "tests/test_local_import_results.py",
    "tests/test_local_import_queue.py",
    "tests/test_local_import_session_service.py",
    "tests/test_celery_app.py",
    "tests/test_celery_context.py",
}


def pytest_collection_modifyitems(config, items):
    """外部サービス依存の大規模結合テストを環境に合わせてスキップ"""

    for item in items:
        path = Path(str(item.fspath))
        try:
            rel_path = path.relative_to(ROOT)
        except ValueError:
            rel_path = path

        normalized = rel_path.as_posix()

        if normalized in ALWAYS_RUN:
            continue

        for pattern, reason in SKIP_RULES:
            if pattern in normalized:
                item.add_marker(pytest.mark.skip(reason=reason))
                break
