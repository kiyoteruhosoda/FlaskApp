"""組み込み(HS256)署名鍵の解決に関するテスト。

``settings.jwt_secret_key`` は環境変数しか参照しないため、管理画面から
``system_settings`` の ``app.config`` に保存された JWT 秘密鍵（および
``DEFAULT_APPLICATION_SETTINGS`` の既定値）を拾えず、``JWT_SECRET_KEY``
環境変数が未設定のステージング等でログインが 500 になっていた。

``resolve_signing_material`` / ``resolve_verification_key`` が
「環境変数 > DB > デフォルト値」の優先順位で鍵を解決することを検証する。
"""
from __future__ import annotations

import os

import jwt

from presentation.fastapi.services.access_token_signing import (
    resolve_signing_material,
    resolve_verification_key,
)
from presentation.fastapi.services.system_setting_service import SystemSettingService


def test_builtin_secret_resolved_from_db_when_env_missing(app_context):
    """環境変数が無くても DB の app.config から鍵を解決できる。"""
    os.environ.pop("JWT_SECRET_KEY", None)

    material = resolve_signing_material()

    assert material.algorithm == "HS256"
    # app_context フィクスチャは DEFAULT_APPLICATION_SETTINGS を app.config に
    # 焼き込んでいるため、既定値 "default-jwt-secret" が解決される。
    assert material.key == "default-jwt-secret"


def test_builtin_secret_prefers_env_over_db(app_context):
    """環境変数が設定されていれば DB 値より優先される。"""
    SystemSettingService.update_application_settings({"JWT_SECRET_KEY": "db-secret"})
    os.environ["JWT_SECRET_KEY"] = "env-secret"

    material = resolve_signing_material()

    assert material.key == "env-secret"


def test_builtin_secret_uses_db_override(app_context):
    """管理画面で保存した値(app.config)が解決される。"""
    os.environ.pop("JWT_SECRET_KEY", None)
    SystemSettingService.update_application_settings({"JWT_SECRET_KEY": "admin-configured"})

    material = resolve_signing_material()

    assert material.key == "admin-configured"


def test_encode_verify_round_trip_without_env(app_context):
    """環境変数無しでも署名→検証のラウンドトリップが成立する。"""
    os.environ.pop("JWT_SECRET_KEY", None)
    SystemSettingService.update_application_settings({"JWT_SECRET_KEY": "round-trip-secret"})

    material = resolve_signing_material()
    token = jwt.encode({"sub": "u+1"}, material.key, algorithm=material.algorithm)

    verification_key = resolve_verification_key("HS256", None)
    decoded = jwt.decode(token, verification_key, algorithms=["HS256"])

    assert decoded["sub"] == "u+1"
