"""``scripts/run_db_migrations.py`` の自己修復フルフローの統合テスト。

STG環境で発生した障害（Alembic管理外で既にテーブルが存在するDBに対して
素朴な ``alembic upgrade head`` を実行し ``Table '...' already exists`` で
失敗する）を、実際に SQLite ファイルDB へテーブルを作った状態から
``run()`` を実行して検証する。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa
import pytest

from tests.integration.test_migration_model_consistency import (
    _load_metadata,
    _setup_test_env,
)

from scripts.run_db_migrations import log_admin_login_self_check, run

ROOT = Path(__file__).resolve().parents[2]


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
def test_legacy_database_with_empty_alembic_version_self_heals(tmp_path):
    """本番障害の再現: テーブルは全部あり、さらに過去の ``upgrade head`` 失敗の
    残骸として**空の** ``alembic_version`` テーブルが存在する状態から復旧できること。

    Alembic はマイグレーション実行前に ``alembic_version`` テーブルを作成するため、
    レガシーDBへの素朴な ``upgrade head`` が ``Table '...' already exists`` で
    失敗すると空の ``alembic_version`` だけが残る。テーブル存在だけで
    「Alembic 管理下」と誤認すると、再起動のたびに同じ CREATE TABLE 失敗を繰り返す。
    """
    _setup_test_env()
    db_path = tmp_path / "legacy-empty-version.db"
    url = f"sqlite:///{db_path}"

    metadata = _load_metadata()
    legacy_engine = sa.create_engine(url)
    try:
        metadata.create_all(legacy_engine)
        with legacy_engine.begin() as conn:
            conn.execute(
                sa.text(
                    "CREATE TABLE alembic_version ("
                    "version_num VARCHAR(32) NOT NULL, "
                    "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
                )
            )
        assert "alembic_version" in _table_names(legacy_engine)
    finally:
        legacy_engine.dispose()

    assert run(url) == 0

    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            version_rows = conn.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).fetchall()
        assert version_rows, "alembic_version にリビジョンが記録されていること"
        # 追いつき適用(upgrade head)でシードデータ投入まで完了していること
        assert _admin_password_hash(engine) is not None
    finally:
        engine.dispose()


@pytest.mark.integration
def test_partial_empty_schema_is_auto_healed(tmp_path):
    """一部テーブルのみ存在し**すべて空**なら「中断された初期構築」として自動復旧すること。

    2026-07-20 の prod ``deploy.sh reset`` の再現: 空DBへの ``init_master`` 適用が
    途中で落ち、作成済みテーブルだけが残った状態からコンテナ再起動でやり直せる。
    """
    _setup_test_env()
    db_path = tmp_path / "partial-empty.db"
    url = f"sqlite:///{db_path}"

    legacy_engine = sa.create_engine(url)
    try:
        with legacy_engine.begin() as conn:
            conn.execute(sa.text('CREATE TABLE "user" (id INTEGER PRIMARY KEY)'))
    finally:
        legacy_engine.dispose()

    assert run(url) == 0

    engine = sa.create_engine(url)
    try:
        tables = _table_names(engine)
        assert "alembic_version" in tables
        # 残骸の user テーブルは削除され、本来のスキーマ＋シードで作り直されている
        assert _admin_password_hash(engine) is not None
    finally:
        engine.dispose()


@pytest.mark.integration
def test_partial_schema_with_data_is_not_auto_healed(tmp_path):
    """一部テーブルのみ存在し**データを持つ**場合は自動判断せずエラー終了すること。

    自動復旧（部分スキーマの削除）は空テーブルに限る。1行でもデータがあれば
    守るべき実データの可能性があるため、何も書き換えずに手動対応へ委ねる。
    """
    _setup_test_env()
    db_path = tmp_path / "partial-with-data.db"
    url = f"sqlite:///{db_path}"

    legacy_engine = sa.create_engine(url)
    try:
        with legacy_engine.begin() as conn:
            conn.execute(sa.text('CREATE TABLE "user" (id INTEGER PRIMARY KEY)'))
            conn.execute(sa.text('INSERT INTO "user" (id) VALUES (1)'))
    finally:
        legacy_engine.dispose()

    assert run(url) == 1

    engine = sa.create_engine(url)
    try:
        # 自動復旧を試みて中途半端に書き換えていないこと(alembic_versionは作られず、データも残る)
        assert "alembic_version" not in _table_names(engine)
        with engine.connect() as conn:
            row = conn.execute(sa.text('SELECT id FROM "user"')).first()
        assert row is not None and row[0] == 1
    finally:
        engine.dispose()


@pytest.mark.integration
def test_run_logs_admin_login_self_check_ok_on_fresh_database(tmp_path, capsys):
    """「ログインできない」障害を毎回 docker exec で調査せずに済むよう、
    起動ログに管理者ログイン可否を明示する自己診断が出ること。
    """
    _setup_test_env()
    os.environ.pop("ADMIN_INITIAL_PASSWORD", None)
    db_path = tmp_path / "selfcheck-ok.db"
    url = f"sqlite:///{db_path}"

    assert run(url) == 0

    captured = capsys.readouterr()
    assert "admin login self-check: OK" in captured.out
    assert "admin@example.com" in captured.out


@pytest.mark.integration
def test_log_admin_login_self_check_warns_on_hash_mismatch(tmp_path, capsys):
    """パスワードハッシュが期待値と一致しない場合、起動を止めずに明確な
    WARNログを出すこと（読み取り専用チェックなので実データは書き換えない）。
    """
    _setup_test_env()
    os.environ.pop("ADMIN_INITIAL_PASSWORD", None)
    db_path = tmp_path / "selfcheck-ng.db"
    url = f"sqlite:///{db_path}"

    assert run(url) == 0
    capsys.readouterr()  # run() 中の出力を捨てる

    engine = sa.create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "UPDATE user SET password_hash = :bogus WHERE email = :email"
                ),
                {"bogus": "scrypt:not-a-real-hash", "email": "admin@example.com"},
            )
    finally:
        engine.dispose()

    log_admin_login_self_check(url)

    captured = capsys.readouterr()
    assert "admin login self-check: NG" in captured.err
    assert "admin@example.com" in captured.err


@pytest.mark.integration
def test_script_runs_as_subprocess_from_project_root(tmp_path):
    """`entrypoint.sh` と同じ呼び出し方（``python scripts/run_db_migrations.py``）で
    サブプロセスとして実行しても ``import shared`` 等が解決できること。

    ``python scripts/run_db_migrations.py`` は、Python の仕様上スクリプト自身の
    ディレクトリ（``scripts/``）だけを sys.path[0] に追加し、プロジェクトルート
    ``ROOT`` は追加しない。pytest 経由で ``import`` した場合は
    ``pyproject.toml`` の ``pythonpath = ["."]`` によりこの問題が隠れてしまう
    （STG環境で ``ModuleNotFoundError: No module named 'shared'`` として
    再現した障害の回帰テスト）。実際に子プロセスとして起動し、pytest 由来の
    ``PYTHONPATH`` 汚染が無い状態を再現する。
    """
    db_path = tmp_path / "subprocess.db"
    url = f"sqlite:///{db_path}"

    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "DATABASE_URI": url,
        "TESTING": "true",
        "SECRET_KEY": "test-secret",
        "JWT_SECRET_KEY": "test-jwt",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "ACCESS_TOKEN_ISSUER": "test",
        "ACCESS_TOKEN_AUDIENCE": "test",
    }

    result = subprocess.run(
        [sys.executable, "scripts/run_db_migrations.py"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "ModuleNotFoundError" not in result.stderr

    engine = sa.create_engine(url)
    try:
        assert "alembic_version" in _table_names(engine)
    finally:
        engine.dispose()
