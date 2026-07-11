"""``scripts/run_db_migrations.py`` の戦略判定ロジック（DB非依存）の単体テスト。

STG環境で "Table 'worker_log' already exists" が発生した障害の原因は、
Alembic管理外で既にテーブルが存在する DB に対して素朴に ``upgrade head`` を
実行し、``init_master`` が全テーブルを CREATE TABLE しようとしたこと。
``decide_strategy`` はこの状況を事前に検出して分岐するための純粋関数。
"""
from __future__ import annotations

from scripts.run_db_migrations import (
    AMBIGUOUS,
    FRESH,
    STAMP_THEN_UPGRADE,
    decide_strategy,
)

TARGET_TABLES = {"user", "role", "permission", "worker_log", "log"}


def test_fresh_database_has_no_tables():
    assert decide_strategy(set(), TARGET_TABLES) == FRESH


def test_already_alembic_managed_database():
    existing = TARGET_TABLES | {"alembic_version"}
    assert decide_strategy(existing, TARGET_TABLES) == FRESH


def test_legacy_database_with_all_tables_but_no_alembic_version():
    """STG障害の再現条件: テーブルは全部あるが alembic_version が無い。"""
    assert decide_strategy(set(TARGET_TABLES), TARGET_TABLES) == STAMP_THEN_UPGRADE


def test_legacy_database_with_extra_unrelated_tables():
    existing = TARGET_TABLES | {"some_other_app_table"}
    assert decide_strategy(existing, TARGET_TABLES) == STAMP_THEN_UPGRADE


def test_partial_schema_is_ambiguous_and_not_auto_healed():
    existing = {"user", "role"}  # 一部だけ
    assert decide_strategy(existing, TARGET_TABLES) == AMBIGUOUS


def test_single_unrelated_table_is_treated_as_fresh():
    """ターゲット外のテーブルしか無ければ新規DB扱い（例: 別用途DBの誤接続ではない前提）。"""
    existing = {"some_other_app_table"}
    assert decide_strategy(existing, TARGET_TABLES) == FRESH
