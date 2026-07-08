"""Alembic マイグレーション環境設定（Flask 非依存）。

Flask-Migrate / Flask アプリコンテキストを廃止し、純粋な Alembic + SQLAlchemy
で動作する env.py に変更した（T11 Flask 完全撤廃の一部）。

実行方法::

    # マイグレーション生成
    alembic revision --autogenerate -m "description"

    # マイグレーション適用
    alembic upgrade head

    # 一つ前のバージョンへロールバック
    alembic downgrade -1

環境変数 ``DATABASE_URI`` または ``.env`` ファイルで接続先を指定する。
"""
from __future__ import annotations

import logging
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

# Alembic Config オブジェクト
config = context.config

# ロギング設定を適用
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")


# ---------------------------------------------------------------------------
# .env のロード
# ---------------------------------------------------------------------------

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv が未インストールの場合はスキップ


# ---------------------------------------------------------------------------
# DB URL 解決
# ---------------------------------------------------------------------------

def _get_database_url() -> str:
    """環境変数 / alembic.ini から DB URL を解決する。"""
    # 環境変数優先
    url = os.environ.get("DATABASE_URI") or os.environ.get("SQLALCHEMY_DATABASE_URI")
    if url:
        return url

    # alembic.ini の sqlalchemy.url
    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url:
        return ini_url

    raise RuntimeError(
        "DATABASE_URI 環境変数または alembic.ini の sqlalchemy.url が設定されていません。"
    )


# ---------------------------------------------------------------------------
# モデル MetaData（autogenerate 用）
# ---------------------------------------------------------------------------

def _load_metadata():
    """全モデルをインポートして MetaData を返す。"""
    from shared.kernel.database.db import db  # noqa: F401 — db.Model を初期化

    # 全モデルを import してメタデータに登録する
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
    import bounded_contexts.picker_import.infrastructure.picker_session  # noqa: F401
    import bounded_contexts.picker_import.infrastructure.picker_import_task  # noqa: F401
    import bounded_contexts.wiki.infrastructure.wiki_models  # noqa: F401
    import bounded_contexts.totp.infrastructure.totp_models  # noqa: F401
    import bounded_contexts.certs.infrastructure.models  # noqa: F401

    return db.metadata


target_metadata = _load_metadata()

# DB URL を alembic コンテキストにセット
database_url = _get_database_url()
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))


# ---------------------------------------------------------------------------
# オフラインモード（URL のみ使用）
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """URL だけを使用してマイグレーションを実行する（DBAPI 不要）。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# オンラインモード（エンジン接続を使用）
# ---------------------------------------------------------------------------

def run_migrations_online() -> None:
    """エンジンを生成して DB に接続し、マイグレーションを実行する。"""

    def process_revision_directives(context, revision, directives):
        """スキーマ変更がない場合は自動生成をスキップする。"""
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("No changes in schema detected.")

    connectable = create_engine(
        _get_database_url(),
        pool_pre_ping=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            process_revision_directives=process_revision_directives,
        )
        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

