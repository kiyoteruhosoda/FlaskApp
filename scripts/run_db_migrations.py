"""起動時に DB マイグレーションを安全に適用するスクリプト（entrypoint から呼び出す）。

過去に Alembic 管理外で構築された DB（旧・焼き込みベースライン `db/init/01_initialize.sql`
経由や、手動 `db.create_all()` 等でテーブルだけ作られ ``alembic_version`` テーブルが
存在しない状態）に対して素朴に ``alembic upgrade head`` を実行すると、
``init_master`` が全テーブルを ``CREATE TABLE`` しようとして
``Table '...' already exists`` で失敗する（STG 環境で再現した障害）。

このスクリプトは適用前に実テーブルの有無と ``alembic_version`` の記録内容を調べ、
以下のパターンに分岐する。

- ``alembic_version`` にリビジョンが記録されている → 既に Alembic 管理下。
  通常どおり upgrade head（差分だけ適用される）
- テーブルが1つも無い（真の新規DB）           → 通常どおり upgrade head
- ``init_master`` が作る全テーブルが揃っている  → 既存スキーマは Alembic 管理外の
  レガシー状態とみなし、``init_master`` へ stamp してから upgrade head
  （``docs/decisions/ADR-0001`` が手動運用として定義していた手順の自動化）
- 一部のテーブルだけ存在する（中途半端な状態）  → 自動判断せずエラー終了し、
  手動調査を促す（誤って中途半端なスキーマを "完了" 扱いしないため）

``alembic_version`` テーブルは「存在する」だけでは Alembic 管理下と判断しない。
Alembic はマイグレーション実行前にこのテーブルを作成するため、レガシーDBに対する
素朴な ``alembic upgrade head`` が ``Table '...' already exists`` で失敗すると、
**空の** ``alembic_version`` テーブルだけが残る（MySQL/MariaDB の DDL は
非トランザクショナルでロールバックされない）。この状態を「管理下」と誤認すると
再起動のたびに同じ CREATE TABLE 失敗を繰り返すため、実際に記録されている
リビジョンの有無で判定する（本番環境で再現した障害）。

さらに、マイグレーションはネームドロックで**直列化**する。web コンテナの
entrypoint（起動時に本スクリプトを実行）と ``deploy.sh``（reset/migrate 時に
``docker exec`` で同じスクリプトを実行）は、reset 直後の空DBに対してほぼ同時に
起動する。両者とも「新規DB(FRESH)」と判定して ``init_master`` の CREATE TABLE を
並行実行すると、``Table 'worker_log' already exists`` (1050) で一方が失敗し
web がクラッシュループする（STG の ``deploy.sh reset`` で再現した障害）。
``decide_strategy`` の冪等判定は同時実行までは守れない（両者が同じ空DBを見て
FRESH を選ぶ）ため、DBレベルのロックで一度に1プロセスだけが適用するようにする。
"""
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "migrations" / "alembic.ini"

# `python scripts/run_db_migrations.py` として直接実行すると、Python は
# スクリプト自身のディレクトリ（scripts/）を sys.path[0] に追加するだけで
# プロジェクトルートは追加しない。そのため `import shared...` が
# `ModuleNotFoundError: No module named 'shared'` になる（entrypoint.sh から
# 実行した際に STG で再現した障害）。cwd や起動方法に依存せず動くよう、
# ここでプロジェクトルートを明示的に sys.path へ追加する。
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE_REVISION = "init_master"

FRESH = "fresh"
STAMP_THEN_UPGRADE = "stamp_then_upgrade"
AMBIGUOUS = "ambiguous"

# 同時マイグレーションを直列化するためのネームドロック。
# init_master + seed のフル適用は数十秒〜数分かかりうるため、待ち側は余裕を
# もってブロックする（先発プロセスの完了後に FRESH の upgrade head が no-op に
# なることを見込む）。
MIGRATION_LOCK_NAME = "photonest_schema_migration"
MIGRATION_LOCK_TIMEOUT_SECONDS = 900


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


def recorded_alembic_revision(
    engine: sa.engine.Engine, existing_tables: set[str]
) -> str | None:
    """``alembic_version`` に実際に記録されているリビジョンを返す（無ければ None）。

    テーブルが存在しても行が無ければ None。Alembic はマイグレーション実行前に
    このテーブルを作るため、レガシーDBへの素朴な upgrade が CREATE TABLE で
    失敗した後は「空の alembic_version テーブル」だけが残る。
    """
    if "alembic_version" not in existing_tables:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).first()
    return row[0] if row else None


def decide_strategy(
    existing_tables: set[str],
    target_tables: set[str],
    recorded_revision: str | None,
) -> str:
    """既存テーブルと記録済みリビジョンから適用戦略を決定する（DB非依存の純粋関数、テスト用に分離）。"""
    if recorded_revision is not None:
        return FRESH  # 既に Alembic が管理している通常経路

    # alembic_version テーブルは「存在するが空」のことがある（過去の upgrade 失敗の残骸）
    # ため、リビジョン記録が無い時点で管理外とみなし、実テーブルの状況で判断する。
    relevant_existing = (existing_tables - {"alembic_version"}) & target_tables
    if not relevant_existing:
        return FRESH  # 真の新規DB

    if target_tables <= existing_tables:
        return STAMP_THEN_UPGRADE  # 全テーブルが揃ったレガシー（Alembic未追跡）DB

    return AMBIGUOUS  # 一部だけ存在する中途半端な状態は自動判断しない


def partial_tables_are_all_empty(engine: sa.engine.Engine, tables: set[str]) -> bool:
    """既存の対象テーブルがすべて0行かどうかを返す（中断された初期構築の判定用）。"""
    if not tables:
        return False
    preparer = engine.dialect.identifier_preparer
    with engine.connect() as conn:
        for table in sorted(tables):
            row = conn.execute(
                sa.text(f"SELECT 1 FROM {preparer.quote(table)} LIMIT 1")
            ).first()
            if row is not None:
                return False
    return True


def heal_interrupted_initial_build(
    engine: sa.engine.Engine,
    existing_tables: set[str],
    target_tables: set[str],
) -> bool:
    """AMBIGUOUS 状態が「中断された初期構築」なら部分スキーマを削除して True を返す。

    2026-07-20 の prod ``deploy.sh reset`` で、空DBへの ``init_master`` 適用が途中で
    落ち（MySQL/MariaDB の DDL は非トランザクショナルなので作成済みテーブルは残る）、
    再起動後の本スクリプトが「一部テーブルのみ存在・リビジョン記録なし」を検出して
    AMBIGUOUS で停止 → web がクラッシュループする障害が起きた。

    この状態は「守るべきデータがあるレガシーDB」とは区別できる: 中断された初期構築
    なら**既存の対象テーブルはすべて0行**のはずである（seed 前に中断している）。
    その場合に限り、部分スキーマ（+ 空の ``alembic_version``）を削除して FRESH
    からやり直す。1行でもデータがあるテーブルが見つかれば何もせず False を返し、
    従来どおり手動対応に委ねる（呼び出し元はロック保持中である前提）。
    """
    relevant = (existing_tables - {"alembic_version"}) & target_tables
    if not partial_tables_are_all_empty(engine, relevant):
        return False

    drop_targets = relevant | ({"alembic_version"} & existing_tables)
    print(
        "[db-migrate] 一部テーブルのみ存在しますが、対象テーブルはすべて空です。"
        "中断された初期構築（init_master 適用中のクラッシュ等）の残骸とみなし、"
        f"部分スキーマ {sorted(drop_targets)} を削除して最初から適用し直します。"
    )
    meta = sa.MetaData()
    meta.reflect(bind=engine, only=sorted(drop_targets))
    meta.drop_all(bind=engine)
    return True


@contextlib.contextmanager
def serialized_migration(engine: sa.engine.Engine):
    """MySQL/MariaDB のネームドロックで同時マイグレーションを直列化する。

    web コンテナの entrypoint と ``deploy.sh`` の ``docker exec`` が、reset 直後の
    空DBに対してほぼ同時に本スクリプトを起動する。両者とも FRESH と判定して
    ``init_master`` の CREATE TABLE を並行実行し ``Table '...' already exists`` で
    衝突する（STG の ``deploy.sh reset`` で再現した障害）。``GET_LOCK`` で直列化
    すると、後発プロセスは先発プロセスの完了を待ってからテーブルと
    ``alembic_version`` を検査する。その時点では既に head まで適用済みのため
    FRESH 経路の ``upgrade head`` が no-op となり衝突しない。

    ロックはコネクション単位で保持されるため、専用コネクションを丸ごと
    マイグレーション完了まで開いたままにする。SQLite などネームドロック
    非対応バックエンドでは何もしない（テスト用）。
    """
    if engine.dialect.name not in ("mysql", "mariadb"):
        yield
        return

    conn = engine.connect()
    try:
        acquired = conn.exec_driver_sql(
            "SELECT GET_LOCK(%s, %s)",
            (MIGRATION_LOCK_NAME, MIGRATION_LOCK_TIMEOUT_SECONDS),
        ).scalar()
        if acquired != 1:
            raise RuntimeError(
                f"DBマイグレーションロック '{MIGRATION_LOCK_NAME}' を "
                f"{MIGRATION_LOCK_TIMEOUT_SECONDS}s 以内に取得できませんでした"
                f"（GET_LOCK の戻り値: {acquired!r}）。別プロセスのマイグレーションが"
                "長時間ロックを保持している可能性があります。"
            )
        try:
            yield
        finally:
            conn.exec_driver_sql("SELECT RELEASE_LOCK(%s)", (MIGRATION_LOCK_NAME,))
    finally:
        conn.close()


def apply_strategy(
    strategy: str,
    existing_tables: set[str],
    target_tables: set[str],
    database_url: str,
) -> int:
    """決定済みの戦略に従って stamp/upgrade を実行する（ロック保持中に呼ぶ前提）。"""
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    if strategy == AMBIGUOUS:
        missing = sorted(target_tables - existing_tables)
        print(
            "[db-migrate] 既存DBのテーブル構成が想定と一致しません"
            f"（不足テーブル: {missing}）。alembic_version が無いまま一部テーブルのみ"
            "存在する中途半端な状態で、かつ既存テーブルにデータが存在するため"
            "自動復旧（空の部分スキーマの削除・再構築）は行いません。"
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


def run(database_url: str) -> int:
    target_tables = load_target_table_names()

    engine = sa.create_engine(database_url, pool_pre_ping=True)
    try:
        # 戦略判定と適用はロック内で一括して行う。判定だけ先に行うと、後発プロセスが
        # 先発プロセスの CREATE TABLE 途中の空DBを見て FRESH を選んでしまう。
        with serialized_migration(engine):
            existing_tables = existing_table_names(engine)
            recorded_revision = recorded_alembic_revision(engine, existing_tables)
            strategy = decide_strategy(existing_tables, target_tables, recorded_revision)
            if strategy == AMBIGUOUS and heal_interrupted_initial_build(
                engine, existing_tables, target_tables
            ):
                existing_tables = existing_table_names(engine)
                strategy = FRESH
            exit_code = apply_strategy(
                strategy, existing_tables, target_tables, database_url
            )
    finally:
        engine.dispose()

    if exit_code != 0:
        return exit_code

    log_admin_login_self_check(database_url)
    return 0


def log_admin_login_self_check(database_url: str) -> None:
    """初期管理者アカウントが実際にログイン可能かを起動ログへ出す（診断専用）。

    「ログインできない」障害は毎回 docker exec でDBを直接見に行かないと原因が
    分からず判断に時間がかかっていたため、起動のたびに自動で検証しログへ残す。
    失敗しても起動は止めない（読み取り専用チェックであり、パスワードを勝手に
    上書きすることはしない — 運用者が意図的に変更した本物のパスワードを
    誤って初期値へ巻き戻すことになるため）。
    """
    from werkzeug.security import check_password_hash

    from shared.domain.auth.master_data import DEFAULT_ADMIN_EMAIL

    admin_initial_password = os.environ.get("ADMIN_INITIAL_PASSWORD")
    expected_password = admin_initial_password or "admin@example.com"
    expected_source = (
        "ADMIN_INITIAL_PASSWORD"
        if admin_initial_password
        else "デフォルト値 'admin@example.com'"
    )

    engine = sa.create_engine(database_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT password_hash, is_active FROM user WHERE email = :email"
                ),
                {"email": DEFAULT_ADMIN_EMAIL},
            ).first()
    except Exception as exc:  # noqa: BLE001 — 診断専用。失敗しても起動は継続する。
        print(
            f"[db-migrate][WARN] admin login self-check をスキップしました: {exc}",
            file=sys.stderr,
        )
        return
    finally:
        engine.dispose()

    if row is None:
        print(
            f"[db-migrate][WARN] admin login self-check: ユーザー "
            f"'{DEFAULT_ADMIN_EMAIL}' が見つかりません。",
            file=sys.stderr,
        )
        return

    password_hash, is_active = row
    if not is_active:
        print(
            f"[db-migrate][WARN] admin login self-check: NG — "
            f"'{DEFAULT_ADMIN_EMAIL}' は is_active=False のためログインできません。",
            file=sys.stderr,
        )
        return

    if check_password_hash(password_hash, expected_password):
        print(
            f"[db-migrate] admin login self-check: OK "
            f"（{DEFAULT_ADMIN_EMAIL} / {expected_source} でログイン可能）"
        )
    else:
        print(
            f"[db-migrate][WARN] admin login self-check: NG — "
            f"'{DEFAULT_ADMIN_EMAIL}' は {expected_source} の資格情報では認証できません。"
            " 既に手動でパスワードを変更済みなら問題ありません。意図しない場合は"
            " ADMIN_INITIAL_PASSWORD を設定して再デプロイするか、"
            " docs/OPERATIONS.md のトラブルシューティングを参照してください。",
            file=sys.stderr,
        )


def main() -> int:
    database_url = get_database_url()
    return run(database_url)


if __name__ == "__main__":
    raise SystemExit(main())
