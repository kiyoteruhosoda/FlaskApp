"""設定の優先順位「環境変数 > DB > デフォルト」の検証。

apply_persisted_settings がデフォルト/DB 値で app.config を組み立てる際、
環境変数が定義されているキーを潰さないこと（.env の ENCRYPTION_KEY が
デフォルト None に上書きされて無視される障害の回帰テスト）。
"""
from __future__ import annotations

import base64

from presentation.web import create_app
from shared.kernel.settings.settings import settings


def test_env_encryption_key_wins_over_default(monkeypatch):
    """.env / 環境変数の ENCRYPTION_KEY がデフォルト（None）に潰されない。"""
    key = "base64:" + base64.urlsafe_b64encode(b"1" * 32).decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)

    app = create_app()
    with app.app_context():
        assert app.config["ENCRYPTION_KEY"] == key
        assert settings.token_encryption_key == key

        # encrypt がその鍵で動作すること（元障害の直接再現）
        from shared.kernel.crypto.crypto import decrypt, encrypt

        assert decrypt(encrypt("hello")) == "hello"


def test_env_value_is_coerced_to_default_type(monkeypatch):
    """Flask が直接参照する数値キーは環境変数でも数値型に変換される。"""
    monkeypatch.setenv("PERMANENT_SESSION_LIFETIME", "2400")

    app = create_app()
    with app.app_context():
        assert app.config["PERMANENT_SESSION_LIFETIME"] == 2400


def test_defaults_still_apply_without_env(monkeypatch):
    """環境変数が無いキーは従来どおりデフォルト値が入る。"""
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)

    app = create_app()
    with app.app_context():
        assert app.config["GOOGLE_CLIENT_ID"] == ""
