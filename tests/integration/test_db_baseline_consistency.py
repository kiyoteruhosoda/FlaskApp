"""``db/init/01_initialize.sql``（DBイメージに焼き込むベースラインSQL）が、現在の
Alembic migration head と同期していることを検証する回帰テスト。

過去、``scripts/regenerate_db_baseline.sh`` による再生成を忘れたまま新しい
migration を追加してしまい、``01_initialize.sql`` のスキーマが古いまま
``alembic_version`` だけ head 扱いになる（あるいは逆に、``alembic_version`` が
空のまま投入され Alembic のバージョン管理と食い違う）不整合が発生した。

このテストは ``01_initialize.sql`` に焼き込まれた ``alembic_version`` の値と、
``migrations/versions/`` から計算した現在の head を突き合わせるだけで、
実際にDBを構築するわけではない（DB接続不要）。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]
BASELINE_SQL = ROOT / "db" / "init" / "01_initialize.sql"

_ALEMBIC_VERSION_INSERT = re.compile(
    r"INSERT INTO `alembic_version`.*?VALUES\s*\(\s*'([0-9a-zA-Z_]+)'\s*\)",
    re.IGNORECASE | re.DOTALL,
)


def _current_head() -> str:
    cfg = Config(str(ROOT / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    script_dir = ScriptDirectory.from_config(cfg)
    heads = script_dir.get_heads()
    assert len(heads) == 1, f"複数のヘッドリビジョンがあります: {heads}"
    return heads[0]


def _baked_in_revision() -> str | None:
    """01_initialize.sql の alembic_version テーブルに INSERT されている revision を取り出す。"""

    sql = BASELINE_SQL.read_text(encoding="utf-8")
    match = _ALEMBIC_VERSION_INSERT.search(sql)
    return match.group(1) if match else None


@pytest.mark.integration
def test_baseline_sql_matches_migration_head():
    """``01_initialize.sql`` が現在の migration head から再生成済みであること。

    ずれている場合は ``./scripts/regenerate_db_baseline.sh`` を実行して
    ``db/init/01_initialize.sql`` を再生成し、コミットし直すこと。
    """

    head = _current_head()
    baked = _baked_in_revision()

    assert baked is not None, (
        "db/init/01_initialize.sql に alembic_version が記録されていません。"
        "./scripts/regenerate_db_baseline.sh で再生成してください。"
    )
    assert baked == head, (
        f"db/init/01_initialize.sql は revision '{baked}' のまま古くなっています"
        f"（現在の migration head は '{head}'）。"
        "./scripts/regenerate_db_baseline.sh で再生成してください。"
    )
