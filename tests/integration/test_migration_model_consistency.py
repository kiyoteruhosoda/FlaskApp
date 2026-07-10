"""マイグレーションとモデル定義の乖離(drift)を検出する回帰テスト。

過去、SQLAlchemy モデルには存在するテーブル/カラムが Alembic マイグレーションに
反映されておらず、``alembic upgrade head`` で構築した DB と実際のモデルが食い違って
いた。これを再発させないため、

  1. 空 DB に全マイグレーションを順次適用し、
  2. その結果スキーマと現行モデル ``db.metadata`` を Alembic autogenerate で比較し、
  3. 差分が無いこと

を検証する。新しいモデル変更を入れたのにマイグレーションを書き忘れると、この
テストが失敗する（= ``alembic revision --autogenerate`` 相当のガード）。

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


def _setup_test_env() -> None:
    """テスト用の最低限の環境変数をセットする。"""
    for key, value in {
        "TESTING": "true",
        "DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret",
        "JWT_SECRET_KEY": "test-jwt",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "ACCESS_TOKEN_ISSUER": "test",
        "ACCESS_TOKEN_AUDIENCE": "test",
    }.items():
        os.environ.setdefault(key, value)


def _load_metadata() -> sa.MetaData:
    """全モデルをインポートして SQLAlchemy MetaData を返す。

    Flask アプリコンテキスト不要。migrations/env.py の _load_metadata() と同様の
    手順でモデルを登録する。
    """
    from shared.kernel.database.db import db  # noqa: F401

    import shared.infrastructure.models.user  # noqa: F401
    import shared.infrastructure.models.passkey  # noqa: F401
    import shared.infrastructure.models.google_account  # noqa: F401
    import shared.infrastructure.models.service_account  # noqa: F401
    import shared.infrastructure.models.service_account_api_key  # noqa: F401
    import shared.infrastructure.models.password_reset_token  # noqa: F401
    import shared.infrastructure.models.job_sync  # noqa: F401
    import shared.infrastructure.models.log  # noqa: F401
    import shared.infrastructure.models.worker_log  # noqa: F401
    import shared.infrastructure.models.celery_task  # noqa: F401
    import shared.infrastructure.models.system_setting  # noqa: F401
    import shared.infrastructure.models.group  # noqa: F401
    import shared.infrastructure.models.user_preference  # noqa: F401
    import shared.infrastructure.models.impersonation_audit_log  # noqa: F401
    import bounded_contexts.photonest.infrastructure.photo_models  # noqa: F401
    import bounded_contexts.photonest.infrastructure.local_import.audit_log_repository  # noqa: F401
    import bounded_contexts.picker_import.infrastructure.picker_session  # noqa: F401
    import bounded_contexts.picker_import.infrastructure.picker_import_task  # noqa: F401
    import bounded_contexts.wiki.infrastructure.wiki_models  # noqa: F401
    import bounded_contexts.totp.infrastructure.totp_models  # noqa: F401
    import bounded_contexts.certs.infrastructure.models  # noqa: F401

    return db.metadata


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

    _setup_test_env()
    metadata = _load_metadata()

    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    try:
        applied = _apply_all_migrations(connection)
        connection.commit()
        assert applied, "適用可能なマイグレーションがありません"

        ctx = MigrationContext.configure(
            connection=connection, opts={"compare_type": True}
        )
        diff = produce_migrations(ctx, metadata)
        ops = diff.upgrade_ops.ops

        assert not ops, (
            "マイグレーションとモデルに乖離があります。"
            "`alembic revision --autogenerate` で差分マイグレーションを追加してください:\n"
            + render_python_code(diff.upgrade_ops)
        )
    finally:
        connection.close()
