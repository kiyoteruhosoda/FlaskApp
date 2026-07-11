"""docker-compose.yml のヘルスチェック猶予時間に関する回帰テスト。

STG の `reset` 実行時、以下の依存チェーンにより `web` は `db` が healthy になった
"後" にしか起動しない:

  db(healthy, 初回は最大600s) → web起動(DB接続待ち + alembic upgrade head
  フル適用 + gunicorn/uvicorn起動) → web(healthy)

`web` のヘルスチェック猶予（``start_period + retries * interval``）が短すぎると、
Synology NAS 等の遅いディスクでは実際には数秒後に正常起動しているにもかかわらず
`docker compose up -d` に unhealthy と誤判定され
"dependency failed to start: container web is unhealthy" でデプロイ全体が
失敗する（実際にSTGで発生した障害）。これの再発を防ぐ。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPOSE_FILE = ROOT / "docker-compose.yml"

_DURATION_RE = re.compile(r"^(\d+)([smh]?)$")


def _to_seconds(value: str) -> int:
    match = _DURATION_RE.match(str(value))
    assert match, f"想定外の時間表記です: {value!r}"
    amount, unit = match.groups()
    multiplier = {"": 1, "s": 1, "m": 60, "h": 3600}[unit]
    return int(amount) * multiplier


def _load_compose() -> dict:
    with COMPOSE_FILE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _healthcheck_budget_seconds(healthcheck: dict) -> int:
    start_period = _to_seconds(healthcheck.get("start_period", "0s"))
    interval = _to_seconds(healthcheck.get("interval", "30s"))
    retries = int(healthcheck.get("retries", 3))
    return start_period + interval * retries


@pytest.mark.unit
def test_web_depends_on_db_healthy():
    """web は db が healthy になってから起動する構成であること（前提の確認）。"""
    compose = _load_compose()
    web = compose["services"]["web"]

    assert web["depends_on"]["db"]["condition"] == "service_healthy"


@pytest.mark.unit
def test_web_healthcheck_has_enough_grace_period_after_db_starts():
    """web のヘルスチェック猶予が、DB接続待ち+フルmigration+gunicorn起動を
    こなすのに十分な長さであること。

    過去の障害では猶予が130s(=40s+3*30s)しか無く、実測でわずかに足りずに
    デプロイが失敗した。DB初期化そのものの遅さ（db の start_period）とは
    独立に、web 自身にも十分な猶予が必要。
    """
    compose = _load_compose()
    web_healthcheck = compose["services"]["web"]["healthcheck"]

    budget = _healthcheck_budget_seconds(web_healthcheck)
    assert budget >= 250, (
        f"web の healthcheck 猶予（start_period + retries*interval）が {budget}s"
        " しかありません。reset直後のフルmigration適用+gunicorn起動が間に合わず"
        " 誤って unhealthy 判定される恐れがあります（250s以上を推奨）。"
    )


@pytest.mark.unit
def test_db_healthcheck_still_has_generous_start_period():
    """db のヘルスチェック start_period が Synology NAS の遅い初回初期化
    （2〜3分実績）に対して十分な余裕を保っていること（既存の対策の回帰防止）。
    """
    compose = _load_compose()
    db_healthcheck = compose["services"]["db"]["healthcheck"]

    start_period = _to_seconds(db_healthcheck.get("start_period", "0s"))
    assert start_period >= 300, (
        f"db の healthcheck start_period が {start_period}s に短縮されています。"
        " 初回初期化が遅い環境で誤って unhealthy 判定される恐れがあります。"
    )
