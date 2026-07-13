"""``scripts/run_db_migrations.py`` の戦略判定ロジック（DB非依存）の単体テスト。

STG環境で "Table 'worker_log' already exists" が発生した障害の原因は、
Alembic管理外で既にテーブルが存在する DB に対して素朴に ``upgrade head`` を
実行し、``init_master`` が全テーブルを CREATE TABLE しようとしたこと。
``decide_strategy`` はこの状況を事前に検出して分岐するための純粋関数。

判定は「``alembic_version`` テーブルの有無」ではなく「実際に記録されている
リビジョンの有無」で行う。Alembic はマイグレーション実行前に
``alembic_version`` テーブルを作成するため、レガシーDBへの素朴な
``upgrade head`` が失敗した後には**空の** ``alembic_version`` テーブルだけが
残り、テーブル存在だけで判定すると再起動のたびに同じ CREATE TABLE 失敗を
繰り返す（本番環境で再現した障害）。
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
    assert decide_strategy(set(), TARGET_TABLES, None) == FRESH


def test_already_alembic_managed_database():
    existing = TARGET_TABLES | {"alembic_version"}
    assert decide_strategy(existing, TARGET_TABLES, "init_master") == FRESH


def test_legacy_database_with_all_tables_but_no_alembic_version():
    """STG障害の再現条件: テーブルは全部あるが alembic_version が無い。"""
    assert decide_strategy(set(TARGET_TABLES), TARGET_TABLES, None) == STAMP_THEN_UPGRADE


def test_legacy_database_with_empty_alembic_version_table():
    """本番障害の再現条件: 過去の upgrade 失敗の残骸として空の alembic_version
    テーブルが存在する。テーブルが在るだけでは管理下と判断せず stamp で復旧する。
    """
    existing = TARGET_TABLES | {"alembic_version"}
    assert decide_strategy(existing, TARGET_TABLES, None) == STAMP_THEN_UPGRADE


def test_empty_alembic_version_on_otherwise_empty_database_is_fresh():
    """空の alembic_version テーブルしか無ければ新規DBとして通常適用する。"""
    assert decide_strategy({"alembic_version"}, TARGET_TABLES, None) == FRESH


def test_legacy_database_with_extra_unrelated_tables():
    existing = TARGET_TABLES | {"some_other_app_table"}
    assert decide_strategy(existing, TARGET_TABLES, None) == STAMP_THEN_UPGRADE


def test_partial_schema_is_ambiguous_and_not_auto_healed():
    existing = {"user", "role"}  # 一部だけ
    assert decide_strategy(existing, TARGET_TABLES, None) == AMBIGUOUS


def test_partial_schema_with_empty_alembic_version_is_ambiguous():
    existing = {"user", "role", "alembic_version"}
    assert decide_strategy(existing, TARGET_TABLES, None) == AMBIGUOUS


def test_single_unrelated_table_is_treated_as_fresh():
    """ターゲット外のテーブルしか無ければ新規DB扱い（例: 別用途DBの誤接続ではない前提）。"""
    existing = {"some_other_app_table"}
    assert decide_strategy(existing, TARGET_TABLES, None) == FRESH
