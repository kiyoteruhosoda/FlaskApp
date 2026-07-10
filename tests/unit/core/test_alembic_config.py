"""alembic.ini の設定と entrypoint の実行パスが正しいことを検証するユニットテスト。

コンテナ起動時に `alembic -c migrations/alembic.ini upgrade head` を
WORKDIR=/app から実行するため、以下を確認する:
  1. migrations/alembic.ini が存在すること
  2. [alembic] セクションに script_location キーが存在すること
  3. script_location の値（migrations）がプロジェクトルートから解決されること
  4. entrypoint.sh が正しい -c オプション付きで alembic を呼び出していること
"""
from __future__ import annotations

import configparser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "migrations" / "alembic.ini"
ENTRYPOINT = ROOT / "scripts" / "entrypoint.sh"


@pytest.mark.unit
def test_alembic_ini_exists():
    """migrations/alembic.ini が存在すること。"""
    assert ALEMBIC_INI.exists(), f"alembic.ini が見つかりません: {ALEMBIC_INI}"


@pytest.mark.unit
def test_alembic_ini_has_script_location():
    """[alembic] セクションに script_location キーが存在すること。"""
    cfg = configparser.ConfigParser()
    cfg.read(str(ALEMBIC_INI))

    assert cfg.has_section("alembic"), "[alembic] セクションがありません"
    assert cfg.has_option("alembic", "script_location"), (
        "script_location キーがありません"
    )


@pytest.mark.unit
def test_alembic_script_location_resolves_from_root():
    """script_location がプロジェクトルートから解決できること。

    コンテナの WORKDIR は /app（= ROOT）。
    `script_location = migrations` なら ROOT/migrations が存在するはず。
    """
    cfg = configparser.ConfigParser()
    cfg.read(str(ALEMBIC_INI))

    script_location = cfg.get("alembic", "script_location")
    resolved = ROOT / script_location
    assert resolved.is_dir(), (
        f"script_location '{script_location}' が ROOT から解決できません: {resolved}"
    )


@pytest.mark.unit
def test_entrypoint_uses_config_flag():
    """entrypoint.sh が `-c migrations/alembic.ini` フラグ付きで alembic を実行していること。

    WORKDIR=/app から `alembic upgrade head` を実行すると alembic.ini が
    見つからず "No 'script_location' key found in configuration" エラーになる。
    `-c migrations/alembic.ini` を指定することで正しく設定を読み込む。
    """
    assert ENTRYPOINT.exists(), f"entrypoint.sh が見つかりません: {ENTRYPOINT}"

    content = ENTRYPOINT.read_text()

    assert "alembic -c migrations/alembic.ini upgrade head" in content, (
        "entrypoint.sh が `-c migrations/alembic.ini` なしで alembic を呼び出しています。"
        "WORKDIR=/app から実行すると alembic.ini が見つからずマイグレーションが失敗します。"
    )
