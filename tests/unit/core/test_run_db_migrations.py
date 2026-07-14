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

from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa

from scripts.run_db_migrations import (
    AMBIGUOUS,
    FRESH,
    MIGRATION_LOCK_NAME,
    STAMP_THEN_UPGRADE,
    decide_strategy,
    serialized_migration,
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


# ---------------------------------------------------------------------------
# serialized_migration: 同時マイグレーションの直列化ロック
#
# STG の `deploy.sh reset` で、web コンテナ entrypoint と deploy.sh の docker exec が
# 空DBへ同時にマイグレーションを走らせ、両者とも FRESH と判定して init_master の
# CREATE TABLE を並行実行し "Table 'worker_log' already exists" (1050) で衝突・
# クラッシュループした障害の回帰テスト。
# ---------------------------------------------------------------------------


def _mock_mysql_engine(get_lock_result):
    """dialect が mysql の疑似 Engine を作る。GET_LOCK の戻り値を差し替えられる。"""
    conn = MagicMock()

    def exec_driver_sql(sql, *args, **kwargs):
        result = MagicMock()
        result.scalar.return_value = (
            get_lock_result if "GET_LOCK" in sql else None
        )
        return result

    conn.exec_driver_sql.side_effect = exec_driver_sql

    engine = MagicMock()
    engine.dialect.name = "mysql"
    engine.connect.return_value = conn
    return engine, conn


def _executed_sql(conn) -> list[str]:
    return [call.args[0] for call in conn.exec_driver_sql.call_args_list]


def test_serialized_migration_is_noop_on_sqlite():
    """SQLite（ネームドロック非対応）ではロックを一切発行しない。"""
    engine = sa.create_engine("sqlite://")
    try:
        with serialized_migration(engine):
            pass
    finally:
        engine.dispose()
    # 何も起きなければ成功（例外が出ないこと）。


def test_serialized_migration_acquires_and_releases_lock_on_mysql():
    engine, conn = _mock_mysql_engine(get_lock_result=1)

    with serialized_migration(engine):
        pass

    sqls = _executed_sql(conn)
    assert any("GET_LOCK" in s for s in sqls)
    assert any("RELEASE_LOCK" in s for s in sqls)
    # GET_LOCK にロック名が渡っていること
    get_lock_call = next(
        c for c in conn.exec_driver_sql.call_args_list if "GET_LOCK" in c.args[0]
    )
    assert get_lock_call.args[1][0] == MIGRATION_LOCK_NAME
    conn.close.assert_called_once()


def test_serialized_migration_releases_lock_even_on_exception():
    """ブロック内で例外が起きてもロックは必ず解放する。"""
    engine, conn = _mock_mysql_engine(get_lock_result=1)

    with pytest.raises(ValueError):
        with serialized_migration(engine):
            raise ValueError("boom")

    sqls = _executed_sql(conn)
    assert any("RELEASE_LOCK" in s for s in sqls)
    conn.close.assert_called_once()


def test_serialized_migration_raises_when_lock_not_acquired():
    """GET_LOCK がタイムアウト(0)を返したら明確なエラーで停止し、ブロックへ入らない。"""
    engine, conn = _mock_mysql_engine(get_lock_result=0)
    entered = False

    with pytest.raises(RuntimeError, match="ロック"):
        with serialized_migration(engine):
            entered = True  # ここへは到達しないはず

    assert entered is False
    # ロックを取得できていないので RELEASE_LOCK は発行しない
    assert not any("RELEASE_LOCK" in s for s in _executed_sql(conn))
    conn.close.assert_called_once()
