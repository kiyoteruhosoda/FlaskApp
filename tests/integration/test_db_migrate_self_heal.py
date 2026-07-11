"""``scripts/run_db_migrations.py`` の自己修復フルフローの統合テスト。

STG環境で発生した障害（Alembic管理外で既にテーブルが存在するDBに対して
素朴な ``alembic upgrade head`` を実行し ``Table '...' already exists`` で
失敗する）を、実際に SQLite ファイルDB へテーブルを作った状態から
``run()`` を実行して検証する。
"""
from __future__ import annotations

import sqlalchemy as sa
import pytest

from tests.integration.test_migration_model_consistency import (
    _load_metadata,
    _setup_test_env,
)

from scripts.run_db_migrations import run


def _admin_password_hash(engine: sa.engine.Engine) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT password_hash FROM user WHERE email = :email"),
            {"email": "admin@example.com"},
        ).first()
    return row[0] if row else None


def _table_names(engine: sa.engine.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


@pytest.mark.integration
def test_fresh_database_runs_upgrade_head(tmp_path):
    _setup_test_env()
    db_path = tmp_path / "fresh.db"
    url = f"sqlite:///{db_path}"

    assert run(url) == 0

    engine = sa.create_engine(url)
    try:
        tables = _table_names(engine)
        assert "alembic_version" in tables
        assert "user" in tables
        assert _admin_password_hash(engine) is not None
    finally:
        engine.dispose()


@pytest.mark.integration
def test_legacy_database_without_alembic_version_self_heals(tmp_path):
    """STG障害の再現: テーブルは全部あるが alembic_version が無い状態から復旧できること。"""
    _setup_test_env()
    db_path = tmp_path / "legacy.db"
    url = f"sqlite:///{db_path}"

    metadata = _load_metadata()
    legacy_engine = sa.create_engine(url)
    try:
        metadata.create_all(legacy_engine)
        assert "alembic_version" not in _table_names(legacy_engine)
    finally:
        legacy_engine.dispose()

    assert run(url) == 0

    engine = sa.create_engine(url)
    try:
        tables = _table_names(engine)
        assert "alembic_version" in tables
        # 追いつき適用(upgrade head)でシードデータ投入まで完了していること
        assert _admin_password_hash(engine) is not None
    finally:
        engine.dispose()


@pytest.mark.integration
def test_partial_legacy_database_is_not_auto_healed(tmp_path):
    """一部テーブルしか無い中途半端な状態は自動判断せずエラー終了すること。"""
    _setup_test_env()
    db_path = tmp_path / "partial.db"
    url = f"sqlite:///{db_path}"

    metadata = _load_metadata()
    legacy_engine = sa.create_engine(url)
    try:
        metadata.create_all(legacy_engine, tables=[metadata.tables["user"]])
    finally:
        legacy_engine.dispose()

    assert run(url) == 1

    engine = sa.create_engine(url)
    try:
        # 自動復旧を試みて中途半端に書き換えていないこと(alembic_versionは作られない)
        assert "alembic_version" not in _table_names(engine)
    finally:
        engine.dispose()
