"""管理者ロールが常にマスタデータ上の全権限コードを保持していることの回帰テスト。

``shared/domain/auth/master_data.py`` の ``PERMISSION_CODES`` は開発の過程で
追加されてきたが、投入は ``2a1f9c0b3d4e_seed_master_data`` が一度だけ実行する
データマイグレーションのため、それより後に追加された権限コードは既存DBの
``role_permissions`` へ自動反映されず、初期管理者でログインしても
「権限がありません」と表示される実害があった
（``0900277b3348_sync_role_permissions_with_master_data`` で修正）。
"""
from __future__ import annotations

import sqlalchemy as sa
import pytest
from alembic import command
from alembic.config import Config

from shared.domain.auth.master_data import DEFAULT_ADMIN_ROLE, PERMISSION_CODES
from tests.integration.test_migration_model_consistency import (
    ROOT,
    _apply_all_migrations,
    _setup_test_env,
)

ALEMBIC_INI = ROOT / "migrations" / "alembic.ini"


def _admin_permission_codes(engine: sa.engine.Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT p.code FROM permission p "
                "JOIN role_permissions rp ON rp.perm_id = p.id "
                "JOIN role r ON r.id = rp.role_id "
                "WHERE r.name = :role"
            ),
            {"role": DEFAULT_ADMIN_ROLE},
        ).fetchall()
    return {row[0] for row in rows}


@pytest.mark.integration
def test_admin_role_has_all_permission_codes_on_fresh_database():
    """新規DBを最新head まで適用した直後、admin ロールは全権限コードを持つこと。"""
    _setup_test_env()

    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    try:
        applied = _apply_all_migrations(connection)
        connection.commit()
        assert applied, "適用可能なマイグレーションがありません"

        # sqlite:// (メモリ) は connection 経由でしか同じDBを見られないため、
        # _admin_permission_codes() は使わず connection 自体に問い合わせる
        rows = connection.execute(
            sa.text(
                "SELECT p.code FROM permission p "
                "JOIN role_permissions rp ON rp.perm_id = p.id "
                "JOIN role r ON r.id = rp.role_id "
                "WHERE r.name = :role"
            ),
            {"role": DEFAULT_ADMIN_ROLE},
        ).fetchall()
        codes = {row[0] for row in rows}

        assert codes == set(PERMISSION_CODES), (
            f"admin ロールに不足している権限: {set(PERMISSION_CODES) - codes}"
        )
    finally:
        connection.close()


@pytest.mark.integration
def test_sync_migration_backfills_permissions_missing_from_legacy_database(tmp_path, monkeypatch):
    """権限コード追加前にシードされた既存DB（一部リンク欠落）でも、
    sync マイグレーションが head まで適用すれば全権限が揃うこと
    （「初期管理者でログインしても権限がありません」の再現・回帰テスト）。
    """
    _setup_test_env()
    db_path = tmp_path / "legacy_permissions.db"
    url = f"sqlite:///{db_path}"

    # migrations/env.py は DATABASE_URI 環境変数を Config の sqlalchemy.url より
    # 優先して自前で再解決するため、ここで一致させておかないと別のDB
    # （_setup_test_env が既定した sqlite:///:memory:）に適用されてしまう。
    monkeypatch.setenv("DATABASE_URI", url)

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)

    # sync マイグレーションの直前（旧コード相当）まで適用
    command.upgrade(cfg, "5a6b39ff7ecc")

    # 権限コード追加前の状態を再現: admin ロールから一部の権限リンクを削除
    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            missing_code = "wiki:admin"
            conn.execute(
                sa.text(
                    "DELETE FROM role_permissions WHERE perm_id IN "
                    "(SELECT id FROM permission WHERE code = :code) "
                    "AND role_id IN (SELECT id FROM role WHERE name = :role)"
                ),
                {"code": missing_code, "role": DEFAULT_ADMIN_ROLE},
            )
        codes_before = _admin_permission_codes(engine)
        assert missing_code not in codes_before
    finally:
        engine.dispose()

    # head まで適用（sync マイグレーションが差分を埋める）
    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
    try:
        codes_after = _admin_permission_codes(engine)
        assert codes_after == set(PERMISSION_CODES), (
            f"sync後もadminロールに不足している権限: {set(PERMISSION_CODES) - codes_after}"
        )
    finally:
        engine.dispose()
