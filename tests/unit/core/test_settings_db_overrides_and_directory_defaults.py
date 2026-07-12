"""settings の解決順「環境変数 > DB(system_settings) > デフォルト値」と
ディレクトリ既定値の一元化に関する回帰テスト。

過去の実害（Photo Settings 画面で顕在化）:

1. ``ApplicationSettings._get`` が環境変数しか参照せず、管理画面で保存した
   DB 設定値（``system_settings`` の ``app.config``）がアプリの動作に一切
   反映されなかった（「設定が生きていない」）。
2. ``settings.py`` の各プロパティと storage の ``_KNOWN_SPECS`` に直書きされた
   既定パスが ``DEFAULT_APPLICATION_SETTINGS`` と食い違っており
   （``/tmp/local_import`` vs ``/app/data/media/local_import`` 等）、
   管理画面の設定定義に表示される既定値と実際に使われるパスがズレていた。
"""
from __future__ import annotations

import json

import pytest
import sqlalchemy as sa

from shared.kernel.settings.settings import ApplicationSettings, settings
from shared.kernel.settings.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
)


# ---------------------------------------------------------------------------
# 2. ディレクトリ既定値の一元化
# ---------------------------------------------------------------------------

_DIRECTORY_PROPERTIES = {
    "MEDIA_LOCAL_IMPORT_DIRECTORY": "storage_local_import_directory",
    "MEDIA_ORIGINALS_DIRECTORY": "storage_originals_directory",
    "MEDIA_THUMBNAILS_DIRECTORY": "storage_thumbs_directory",
    "MEDIA_PLAYBACK_DIRECTORY": "storage_play_directory",
    "MEDIA_TEMP_DIRECTORY": "tmp_directory",
    "SYSTEM_BACKUP_DIRECTORY": "backup_directory",
    "MEDIA_UPLOAD_TEMP_DIRECTORY": "upload_tmp_directory",
}


@pytest.mark.unit
@pytest.mark.parametrize("config_key,property_name", sorted(_DIRECTORY_PROPERTIES.items()))
def test_directory_properties_fall_back_to_canonical_defaults(config_key, property_name):
    """未設定時のディレクトリは DEFAULT_APPLICATION_SETTINGS の既定値になること。"""
    isolated = ApplicationSettings(env={})
    resolved = getattr(isolated, property_name)
    assert str(resolved) == str(DEFAULT_APPLICATION_SETTINGS[config_key]), (
        f"{property_name} の既定値が DEFAULT_APPLICATION_SETTINGS[{config_key}] と"
        "食い違っています（管理画面の設定定義と実際のパスがズレます）"
    )


@pytest.mark.unit
def test_storage_specs_defaults_match_canonical_defaults():
    """storage コンテキストの _KNOWN_SPECS 既定値も正本と一致すること。"""
    from bounded_contexts.storage.infrastructure.filesystem.local import _KNOWN_SPECS

    for spec in _KNOWN_SPECS:
        canonical = str(DEFAULT_APPLICATION_SETTINGS[spec.config_key])
        assert spec.defaults == (canonical,), (
            f"_KNOWN_SPECS[{spec.config_key}] の既定値 {spec.defaults} が"
            f" 正本 {canonical!r} と食い違っています"
        )


# ---------------------------------------------------------------------------
# 1. DB(system_settings) 上書き層
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_backed_settings(tmp_path):
    """system_settings テーブルを持つ実DBへ legacy scoped session を束ね、
    グローバル settings の DB 上書き層が読める状態を作る。"""
    from shared.kernel.database.db import db

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'settings.db'}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE system_settings ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "setting_key VARCHAR(100) NOT NULL UNIQUE, "
                "setting_json TEXT NOT NULL, "
                "description TEXT, "
                "updated_at DATETIME)"
            )
        )
    db.init_app_engine(engine)
    settings.reload_db_overrides()
    try:
        yield engine
    finally:
        settings.reload_db_overrides()
        engine.dispose()


def _store_app_config(engine: sa.engine.Engine, payload: dict) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.text("DELETE FROM system_settings WHERE setting_key = 'app.config'")
        )
        conn.execute(
            sa.text(
                "INSERT INTO system_settings (setting_key, setting_json) "
                "VALUES ('app.config', :payload)"
            ),
            {"payload": json.dumps(payload)},
        )


@pytest.mark.integration
def test_db_stored_setting_takes_effect(db_backed_settings, monkeypatch):
    """管理画面で保存した値（DB）が settings 経由で実際に反映されること。"""
    monkeypatch.delenv("MEDIA_LOCAL_IMPORT_DIRECTORY", raising=False)
    _store_app_config(
        db_backed_settings,
        {"MEDIA_LOCAL_IMPORT_DIRECTORY": "/nas/photos/import"},
    )
    settings.reload_db_overrides()

    assert str(settings.storage_local_import_directory) == "/nas/photos/import"
    assert settings.local_import_directory_configured == "/nas/photos/import"


@pytest.mark.integration
def test_environment_variable_wins_over_db(db_backed_settings, monkeypatch):
    """優先順位: 環境変数 > DB。両方ある場合は環境変数が勝つこと。"""
    _store_app_config(
        db_backed_settings,
        {"MEDIA_LOCAL_IMPORT_DIRECTORY": "/nas/photos/import"},
    )
    settings.reload_db_overrides()
    monkeypatch.setenv("MEDIA_LOCAL_IMPORT_DIRECTORY", "/env/wins")

    assert str(settings.storage_local_import_directory) == "/env/wins"


@pytest.mark.integration
def test_db_unavailable_falls_back_to_defaults(monkeypatch, tmp_path):
    """DB が読めない場合は黙ってデフォルト値で動作すること（起動順序の安全性）。"""
    from shared.kernel.database.db import db

    monkeypatch.delenv("MEDIA_LOCAL_IMPORT_DIRECTORY", raising=False)
    # system_settings テーブルの無い空DBに束ねる
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    db.init_app_engine(engine)
    settings.reload_db_overrides()
    try:
        assert str(settings.storage_local_import_directory) == str(
            DEFAULT_APPLICATION_SETTINGS["MEDIA_LOCAL_IMPORT_DIRECTORY"]
        )
    finally:
        settings.reload_db_overrides()
        engine.dispose()


@pytest.mark.unit
def test_explicit_env_instance_never_consults_db():
    """明示的に env マッピングを渡したインスタンス（テスト用）は DB を見ないこと。"""
    isolated = ApplicationSettings(env={})
    assert isolated._db_overrides is None


@pytest.mark.integration
def test_upsert_invalidates_cache_immediately(db_backed_settings, monkeypatch):
    """SystemSettingService の保存は TTL を待たず即時反映されること。"""
    from presentation.fastapi.services.system_setting_service import (
        SystemSettingService,
    )

    monkeypatch.delenv("MEDIA_LOCAL_IMPORT_DIRECTORY", raising=False)

    # 一度デフォルトで解決させてキャッシュを温める
    assert str(settings.storage_local_import_directory) == str(
        DEFAULT_APPLICATION_SETTINGS["MEDIA_LOCAL_IMPORT_DIRECTORY"]
    )

    SystemSettingService.upsert_application_config(
        {"MEDIA_LOCAL_IMPORT_DIRECTORY": "/nas/updated/import"}
    )

    assert str(settings.storage_local_import_directory) == "/nas/updated/import", (
        "設定保存後もキャッシュされた旧値が返っています（invalidate が効いていない）"
    )
