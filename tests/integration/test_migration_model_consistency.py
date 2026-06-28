"""マイグレーションとモデル定義の乖離(drift)を検出する回帰テスト。

過去、SQLAlchemy モデルには存在するテーブル/カラムが Alembic マイグレーションに
反映されておらず、``flask db upgrade`` で構築した DB と実際のモデルが食い違って
いた。これを再発させないため、

  1. 空 DB に全マイグレーションを順次適用し、
  2. その結果スキーマと現行モデル ``db.metadata`` を Alembic autogenerate で比較し、
  3. 差分が無いこと

を検証する。新しいモデル変更を入れたのにマイグレーションを書き忘れると、この
テストが失敗する（= ``flask db migrate`` 相当のガード）。

注: SQLite 上での比較のため MariaDB 固有の型差異までは検出しないが、テーブル・
カラム・インデックス・制約レベルの乖離は確実に検出できる。
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import produce_migrations, render_python_code
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]


def _build_app():
    os.environ.setdefault("TESTING", "true")
    for key, value in {
        "DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret",
        "JWT_SECRET_KEY": "test-jwt",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "ACCESS_TOKEN_ISSUER": "test",
        "ACCESS_TOKEN_AUDIENCE": "test",
    }.items():
        os.environ.setdefault(key, value)

    from presentation.web import create_app
    from tests.config import TestConfig

    app = create_app()
    app.config.from_object(TestConfig)
    return app


def _apply_all_migrations(connection) -> list[str]:
    """全マイグレーションをベース→ヘッド順に空 DB へ適用する。"""

    cfg = Config(str(ROOT / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    script_dir = ScriptDirectory.from_config(cfg)

    # walk_revisions は head -> base。base -> head に並べ替える。
    ordered = list(reversed(list(script_dir.walk_revisions())))

    ctx = MigrationContext.configure(connection)
    for script in ordered:
        spec = importlib.util.spec_from_file_location(
            f"_mig_{script.revision}", script.path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with Operations.context(ctx):
            module.upgrade()
    return [script.revision for script in ordered]


@pytest.mark.integration
def test_single_head_and_base():
    """ベースとヘッドがそれぞれ 1 つだけであること(履歴分岐の検出)。"""

    cfg = Config(str(ROOT / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    script_dir = ScriptDirectory.from_config(cfg)

    assert len(script_dir.get_bases()) == 1, (
        f"複数のベースリビジョンがあります: {script_dir.get_bases()}"
    )
    assert len(script_dir.get_heads()) == 1, (
        f"複数のヘッドリビジョンがあります: {script_dir.get_heads()}"
    )


@pytest.mark.integration
def test_migrations_match_models():
    """全マイグレーション適用後のスキーマがモデル定義と一致すること。"""

    app = _build_app()

    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    try:
        applied = _apply_all_migrations(connection)
        connection.commit()
        assert applied, "適用可能なマイグレーションがありません"

        from presentation.web.bootstrap.extensions import db

        with app.app_context():
            ctx = MigrationContext.configure(
                connection=connection, opts={"compare_type": True}
            )
            diff = produce_migrations(ctx, db.metadata)
            ops = diff.upgrade_ops.ops

        assert not ops, (
            "マイグレーションとモデルに乖離があります。"
            "`flask db migrate` で差分マイグレーションを追加してください:\n"
            + render_python_code(diff.upgrade_ops)
        )
    finally:
        connection.close()
