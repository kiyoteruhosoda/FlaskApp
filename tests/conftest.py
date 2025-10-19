import os
import sys
from pathlib import Path

import pytest

from core.system_settings_defaults import (
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
        "FEATURE_X_DB_URI": "",
        "ACCESS_TOKEN_ISSUER": "test-issuer",
        "ACCESS_TOKEN_AUDIENCE": "test-audience",
    }
    
    for key, value in test_env.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value
    
    try:
        # configモジュールをリロード
        import webapp.config as config_module
        importlib.reload(config_module)

        from webapp import create_app
        from webapp.config import TestConfig
        from webapp.extensions import db
        from webapp.services.system_setting_service import SystemSettingService
        from webapp import _apply_persisted_settings

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
