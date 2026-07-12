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

        # 環境変数を復元した「後」で fastapi config を正規化する。
        config_module = sys.modules.get("presentation.fastapi.config")
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
    """Flask-specific cache reset hook (now a no-op in FastAPI)."""
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
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        from shared.kernel.database.db import db
        from presentation.fastapi.services.system_setting_service import SystemSettingService

        # すべての ORM モデルをメタデータに登録してから create_all() を呼ぶ
        import shared.infrastructure.models  # noqa: F401
        from shared.infrastructure.models.impersonation_audit_log import ImpersonationAuditLog  # noqa: F401
        from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession  # noqa: F401
        from bounded_contexts.photonest.infrastructure import photo_models as _pm  # noqa: F401
        from bounded_contexts.wiki.infrastructure import wiki_models as _wm  # noqa: F401
        from bounded_contexts.certs.infrastructure.models import (  # noqa: F401
            CertificateGroupEntity, IssuedCertificateEntity, CertificatePrivateKeyEntity,
        )
        from bounded_contexts.totp.infrastructure.totp_models import TOTPCredential  # noqa: F401

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        db.init_app_engine(engine)

        db.create_all(bind=engine)
        payload = dict(DEFAULT_APPLICATION_SETTINGS)
        for key in payload.keys():
            payload[key] = _coerce_env_value(key, payload[key])
        SystemSettingService.upsert_application_config(payload)

        cors_raw = os.environ.get("CORS_ALLOWED_ORIGINS")
        if cors_raw:
            allowed_origins = [segment.strip() for segment in cors_raw.split(",") if segment.strip()]
        else:
            allowed_origins = list(DEFAULT_CORS_SETTINGS.get("allowedOrigins", []))
        SystemSettingService.upsert_cors_config(allowed_origins)

        yield engine
        db.session.remove()
        db.drop_all(bind=engine)
    finally:
        # 環境変数を元に戻す
        for key, original_value in original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
        # settings の DB 上書きキャッシュ（TTL）を破棄し、このテストの
        # インメモリ DB の値が後続テストへ漏れないようにする
        from shared.kernel.settings.settings import settings as _settings
        _settings.reload_db_overrides()


# NOTE: かつて存在した ``pytest_collection_modifyitems`` によるパスベースの
# 一括 skip（SKIP_RULES / ALWAYS_RUN）はテスト再編で全パターンが陳腐化したため
# 撤去した。外部依存のテストは各テスト側で skipif 等により条件付き制御する。
