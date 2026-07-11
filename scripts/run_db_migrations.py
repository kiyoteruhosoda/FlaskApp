"""起動時に DB マイグレーションを安全に適用するスクリプト（entrypoint から呼び出す）。

過去に Alembic 管理外で構築された DB（旧・焼き込みベースライン `db/init/01_initialize.sql`
経由や、手動 `db.create_all()` 等でテーブルだけ作られ ``alembic_version`` テーブルが
存在しない状態）に対して素朴に ``alembic upgrade head`` を実行すると、
``init_master`` が全テーブルを ``CREATE TABLE`` しようとして
``Table '...' already exists`` で失敗する（STG 環境で再現した障害）。

このスクリプトは適用前に実テーブルの有無を調べ、以下の3パターンに分岐する。

- テーブルが1つも無い（真の新規DB）           → 通常どおり upgrade head
- ``init_master`` が作る全テーブルが揃っている  → 既存スキーマは Alembic 管理外の
  レガシー状態とみなし、``init_master`` へ stamp してから upgrade head
  （``docs/decisions/ADR-0001`` が手動運用として定義していた手順の自動化）
- 一部のテーブルだけ存在する（中途半端な状態）  → 自動判断せずエラー終了し、
  手動調査を促す（誤って中途半端なスキーマを "完了" 扱いしないため）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "migrations" / "alembic.ini"

BASELINE_REVISION = "init_master"

FRESH = "fresh"
STAMP_THEN_UPGRADE = "stamp_then_upgrade"
AMBIGUOUS = "ambiguous"


def get_database_url() -> str:
    """env.py と同じ優先順位（環境変数 > alembic.ini）で DB URL を解決する。"""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    url = os.environ.get("DATABASE_URI") or os.environ.get("SQLALCHEMY_DATABASE_URI")
    if url:
        return url

    cfg = Config(str(ALEMBIC_INI))
    ini_url = cfg.get_main_option("sqlalchemy.url")
    if ini_url:
        return ini_url

    raise RuntimeError(
        "DATABASE_URI 環境変数または alembic.ini の sqlalchemy.url が設定されていません。"
    )


def load_target_table_names() -> set[str]:
    """init_master が作成する全テーブル名を現行モデル定義から取得する。"""
    from shared.kernel.database.db import db  # noqa: F401 — db.Model を初期化

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

    return set(db.metadata.tables.keys())


def existing_table_names(engine: sa.engine.Engine) -> set[str]:
    inspector = sa.inspect(engine)
    return set(inspector.get_table_names())


def decide_strategy(existing_tables: set[str], target_tables: set[str]) -> str:
    """既存テーブルの状況から適用戦略を決定する（DB非依存の純粋関数、テスト用に分離）。"""
    if "alembic_version" in existing_tables:
        return FRESH  # 既に Alembic が管理している通常経路

    relevant_existing = existing_tables & target_tables
    if not relevant_existing:
        return FRESH  # 真の新規DB

    if target_tables <= existing_tables:
        return STAMP_THEN_UPGRADE  # 全テーブルが揃ったレガシー（Alembic未追跡）DB

    return AMBIGUOUS  # 一部だけ存在する中途半端な状態は自動判断しない


def run(database_url: str) -> int:
    engine = sa.create_engine(database_url, pool_pre_ping=True)
    try:
        existing_tables = existing_table_names(engine)
    finally:
        engine.dispose()

    target_tables = load_target_table_names()
    strategy = decide_strategy(existing_tables, target_tables)

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    if strategy == AMBIGUOUS:
        missing = sorted(target_tables - existing_tables)
        print(
            "[db-migrate] 既存DBのテーブル構成が想定と一致しません"
            f"（不足テーブル: {missing}）。alembic_version が無いまま一部テーブルのみ"
            "存在する中途半端な状態のため、自動復旧を中止します。"
            " docs/OPERATIONS.md のトラブルシューティングを参照し、手動で調査・"
            "対応してください。",
            file=sys.stderr,
        )
        return 1

    # migrations/env.py は DATABASE_URI 環境変数を Config の sqlalchemy.url より
    # 優先して自前で再解決するため、ここで確実に一致させておく
    # （さもないと本関数の判定対象DBと実際にマイグレーションが適用されるDBが
    # ずれる可能性がある）。
    previous_database_uri = os.environ.get("DATABASE_URI")
    os.environ["DATABASE_URI"] = database_url
    try:
        if strategy == STAMP_THEN_UPGRADE:
            print(
                f"[db-migrate] 既存DBに {BASELINE_REVISION} 相当のテーブルが "
                "Alembic 管理外で既に存在します。alembic_version を "
                f"{BASELINE_REVISION} へ stamp してから upgrade head を実行します。"
            )
            command.stamp(cfg, BASELINE_REVISION)

        command.upgrade(cfg, "head")
    finally:
        if previous_database_uri is None:
            os.environ.pop("DATABASE_URI", None)
        else:
            os.environ["DATABASE_URI"] = previous_database_uri

    return 0


def main() -> int:
    database_url = get_database_url()
    return run(database_url)


if __name__ == "__main__":
    raise SystemExit(main())
