"""DB 等に永続化された設定値を ``app.config`` へ反映する処理.

``create_app()`` から切り出した起動時設定ロードを担う。アプリケーション設定・
CORS 設定・メール設定を取得し、既定値とレガシーキーを考慮して ``app.config`` を
組み立てる。管理画面での設定更新後にも再適用される（公開関数
``apply_persisted_settings``）。

また、Gunicorn の複数ワーカー構成では「設定更新リクエストを処理したワーカー」
以外は再起動まで古い ``app.config`` を持ち続けてしまうため、リクエストごとに
（最大 ``_STALENESS_CHECK_INTERVAL_SECONDS`` 間隔で）``system_settings`` の
``updated_at`` を確認し、更新されていれば再適用する
``refresh_persisted_settings_if_stale`` を提供する。
"""

from __future__ import annotations

import os
import time
from collections.abc import MutableMapping

from flask import Flask

from shared.kernel.settings.settings import settings
from shared.kernel.settings.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_CORS_SETTINGS,
)

from presentation.web.services.system_setting_service import SystemSettingService

# 鮮度チェックの最小間隔（秒）。この間隔内の連続リクエストでは DB を見ない。
_STALENESS_CHECK_INTERVAL_SECONDS = 10.0
_LAST_CHECK_MONOTONIC_KEY = "_PERSISTED_SETTINGS_LAST_CHECK_MONOTONIC"
_APPLIED_UPDATED_AT_KEY = "_PERSISTED_SETTINGS_APPLIED_UPDATED_AT"


def _coerce_env_value(raw: str, default_value):
    """環境変数の文字列値を、デフォルト値の型に合わせて変換する。

    Flask 自身が参照するキー（PERMANENT_SESSION_LIFETIME 等）が文字列のまま
    app.config に入ると誤動作するため、bool / int / float / list は変換する。
    変換できない場合は文字列のまま返す（設定側の get_int 等が再変換する）。
    """

    if isinstance(default_value, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default_value, int) and not isinstance(default_value, bool):
        try:
            return int(raw.strip())
        except ValueError:
            return raw
    if isinstance(default_value, float):
        try:
            return float(raw.strip())
        except ValueError:
            return raw
    if isinstance(default_value, (list, tuple)):
        return [segment.strip() for segment in raw.split(",") if segment.strip()]
    return raw


def _latest_settings_updated_at():
    """system_settings 全体の最終更新時刻を返す（テーブル未作成時は例外）。"""

    from shared.infrastructure.models.system_setting import SystemSetting
    from shared.kernel.database.db import db

    return db.session.query(db.func.max(SystemSetting.updated_at)).scalar()


def refresh_persisted_settings_if_stale(app: Flask) -> None:
    """DB の設定が更新されていれば ``app.config`` へ再適用する。

    設定更新を処理していないワーカーにも変更を波及させるための仕組み。
    チェックは ``_STALENESS_CHECK_INTERVAL_SECONDS`` ごとに 1 クエリで、
    DB 不通時・テーブル未作成時は何もしない（現在の設定のまま動き続ける）。
    """

    if app.config.get("TESTING"):
        return

    now = time.monotonic()
    last_check = app.config.get(_LAST_CHECK_MONOTONIC_KEY)
    if last_check is not None and (now - last_check) < _STALENESS_CHECK_INTERVAL_SECONDS:
        return
    app.config[_LAST_CHECK_MONOTONIC_KEY] = now

    try:
        latest = _latest_settings_updated_at()
    except Exception:  # pragma: no cover - DB 不通時は既存設定のまま
        return
    if latest is None:
        return

    applied = app.config.get(_APPLIED_UPDATED_AT_KEY)
    if applied is not None and latest <= applied:
        return

    app.logger.info(
        "Persisted settings changed in DB (updated_at=%s); reloading into app.config",
        latest,
    )
    apply_persisted_settings(app)


def apply_persisted_settings(app: Flask) -> None:
    """Load persisted configuration values into ``app.config``."""

    # 再適用の判定基準として、読み込み開始時点の最終更新時刻を控える
    try:
        app.config[_APPLIED_UPDATED_AT_KEY] = _latest_settings_updated_at()
    except Exception:  # pragma: no cover - 起動直後などテーブル未作成時
        app.config[_APPLIED_UPDATED_AT_KEY] = None

    try:
        stored_payload = SystemSettingService.load_application_config_payload()
    except Exception as exc:  # pragma: no cover - defensive fallback
        app.logger.warning("Failed to load application settings from DB: %s", exc)
        stored_payload = {}

    config_payload = dict(DEFAULT_APPLICATION_SETTINGS)
    config_payload.update(stored_payload)

    if stored_payload:
        for canonical_key, legacy_keys in settings._LEGACY_KEYS.items():
            if canonical_key in stored_payload:
                continue
            for legacy_key in legacy_keys:
                if legacy_key in stored_payload:
                    config_payload[canonical_key] = stored_payload[legacy_key]
                    break
    for key, value in config_payload.items():
        if key == "DATABASE_URI":
            continue
        # 優先順位は「環境変数 > DB > デフォルト」（CLAUDE.md）。設定解決は
        # app.config を最初に参照するため、環境変数が定義されているキーは
        # env 値（デフォルトの型に合わせて変換）を書き込み、DB/デフォルト値で
        # 上書きしない。これが無いと .env の ENCRYPTION_KEY 等が
        # デフォルト（None）に潰されて無視される。
        env_raw = os.environ.get(key)
        if env_raw is not None:
            app.config[key] = _coerce_env_value(
                env_raw, DEFAULT_APPLICATION_SETTINGS.get(key)
            )
            continue
        if isinstance(value, dict):
            app.config[key] = dict(value)
        elif isinstance(value, list):
            app.config[key] = list(value)
        else:
            app.config[key] = value

    if "REMEMBER_COOKIE_SECURE" not in config_payload:
        app.config["REMEMBER_COOKIE_SECURE"] = bool(
            app.config.get("SESSION_COOKIE_SECURE", False)
        )

    try:
        cors_payload = SystemSettingService.load_cors_config()
    except Exception as exc:  # pragma: no cover - defensive fallback
        app.logger.warning("Failed to load CORS settings from DB: %s", exc)
        cors_payload = dict(DEFAULT_CORS_SETTINGS)
    allowed = cors_payload.get("allowedOrigins", [])
    if isinstance(allowed, str):
        allowed_origins = [segment.strip() for segment in allowed.split(",") if segment.strip()]
    elif isinstance(allowed, (list, tuple, set)):
        allowed_origins = [str(origin).strip() for origin in allowed if str(origin).strip()]
    else:
        allowed_origins = []
    app.config["CORS_ALLOWED_ORIGINS"] = tuple(allowed_origins)

    # メール設定を再適用
    from .extensions import mail

    mail_enabled = bool(config_payload.get("MAIL_ENABLED", False))

    if mail_enabled:
        app.config["MAIL_SERVER"] = config_payload.get("MAIL_SERVER", "")
        app.config["MAIL_PORT"] = config_payload.get("MAIL_PORT", 587)
        app.config["MAIL_USE_TLS"] = config_payload.get("MAIL_USE_TLS", True)
        app.config["MAIL_USE_SSL"] = config_payload.get("MAIL_USE_SSL", False)
        app.config["MAIL_USERNAME"] = config_payload.get("MAIL_USERNAME", "")
        app.config["MAIL_PASSWORD"] = config_payload.get("MAIL_PASSWORD", "")
        app.config["MAIL_DEFAULT_SENDER"] = config_payload.get("MAIL_DEFAULT_SENDER") or config_payload.get("MAIL_USERNAME", "")

        mail_state = mail.init_app(app)
        mail.state = mail_state
        mail.app = app
    else:
        extensions = getattr(app, "extensions", None)
        if isinstance(extensions, MutableMapping):
            extensions.pop("mailman", None)
        mail.state = None
        mail.app = None
