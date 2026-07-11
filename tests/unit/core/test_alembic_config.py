"""alembic.ini の設定と entrypoint の実行パスが正しいことを検証するユニットテスト。

コンテナ起動時に `scripts/run_db_migrations.py`（内部で
`migrations/alembic.ini` を絶対パスで解決して alembic を呼び出す）を
WORKDIR=/app から実行するため、以下を確認する:
  1. migrations/alembic.ini が存在すること
  2. [alembic] セクションに script_location キーが存在すること
  3. script_location の値（migrations）がプロジェクトルートから解決されること
  4. entrypoint.sh が migrations 用スクリプトを呼び出していること
"""
from __future__ import annotations

import configparser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = ROOT / "migrations" / "alembic.ini"
ENTRYPOINT = ROOT / "scripts" / "entrypoint.sh"
DEPLOY_SCRIPTS = [ROOT / "scripts" / "deploy.sh", ROOT / "scripts" / "deploy-stg.sh"]


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
def test_entrypoint_uses_migration_script():
    """entrypoint.sh が `scripts/run_db_migrations.py` を実行していること。

    素朴に `alembic upgrade head` を実行すると、Alembic管理外で既にテーブルが
    存在する DB（過去の焼き込みベースライン運用の名残等）に対して
    `Table '...' already exists` で失敗する（STG環境で再現した障害）。
    `scripts/run_db_migrations.py` は事前にテーブルの有無を調べ、
    未追跡の既存スキーマなら `stamp` してから `upgrade head` する自己修復を行う。
    """
    assert ENTRYPOINT.exists(), f"entrypoint.sh が見つかりません: {ENTRYPOINT}"

    content = ENTRYPOINT.read_text()

    assert "python scripts/run_db_migrations.py" in content, (
        "entrypoint.sh が scripts/run_db_migrations.py を呼び出していません。"
    )


@pytest.mark.unit
def test_migration_script_resolves_alembic_ini_by_absolute_path():
    """run_db_migrations.py が cwd に依存せず alembic.ini を解決すること。

    WORKDIR=/app 以外から実行されても `No 'script_location' key found in
    configuration` にならないよう、`Path(__file__)` 基準の絶対パスを使う。
    """
    from scripts.run_db_migrations import ALEMBIC_INI as script_alembic_ini

    assert script_alembic_ini.is_absolute()
    assert script_alembic_ini == ALEMBIC_INI


@pytest.mark.unit
@pytest.mark.parametrize("deploy_script", DEPLOY_SCRIPTS, ids=lambda p: p.name)
def test_deploy_scripts_use_migration_script_not_bare_alembic(deploy_script: Path):
    """deploy.sh / deploy-stg.sh が `docker compose exec web alembic ...` を
    `-c` フラグ無しで直接呼んでいないこと。

    WORKDIR=/app にはプロジェクトルート用の alembic.ini が無いため、
    `alembic upgrade head` を素で実行すると
    "No 'script_location' key found in configuration" で失敗する。
    `scripts/run_db_migrations.py`（絶対パスで alembic.ini を解決する）経由で
    呼び出す必要がある。
    """
    assert deploy_script.exists(), f"見つかりません: {deploy_script}"

    content = deploy_script.read_text()

    assert "python scripts/run_db_migrations.py" in content, (
        f"{deploy_script.name} が scripts/run_db_migrations.py を呼び出していません。"
    )
    assert "exec -T web alembic " not in content, (
        f"{deploy_script.name} が `-c migrations/alembic.ini` の無い素の alembic を"
        " 直接呼び出しています。"
    )
