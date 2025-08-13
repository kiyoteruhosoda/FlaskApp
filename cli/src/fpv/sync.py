from __future__ import annotations
from typing import Optional, Dict, Any, List
from sqlalchemy import text
from .db import get_engine_from_env
from .logs import log, new_trace_id


def run_sync(all_accounts: bool = True,
             account_id: Optional[int] = None,
             dry_run: bool = True) -> int:
    """
    Returns: exit code (0=success, 1=partial/failed)
    """
    trace = new_trace_id()
    eng = get_engine_from_env()

    # アカウント抽出
    sql = "SELECT id, account_email, oauth_token_json FROM google_account WHERE status='active'"
    params: Dict[str, Any] = {}
    if not all_accounts and account_id is not None:
        sql += " AND id=:id"
        params["id"] = account_id

    with eng.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    if not rows:
        log("sync.no_accounts", trace=trace)
        return 0

    overall_failed = 0

    for r in rows:
        aid, email, token_json = int(r[0]), r[1], r[2]
        log("sync.account.begin", trace=trace, account_id=aid, email=email, dry_run=dry_run)

        # ジョブ開始
        with eng.begin() as conn:
            job_id = conn.execute(
                text("INSERT INTO job_sync (target, account_id, started_at, status, stats_json) "
                     "VALUES ('google_photos', :aid, UTC_TIMESTAMP(), 'running', :stats)"),
                {"aid": aid, "stats": "{}"}
            ).lastrowid

        # ダミー処理（dry-run）: 3件処理した体で統計を出す
        stats: Dict[str, Any] = {"new": 3, "dup": 0, "failed": 0}
        status = "success"

        # 例外処理の雛形（将来: API/IOエラーで failed/partial 更新）
        try:
            if dry_run:
                # ここでは何もしない（ログだけ）
                for i in range(1, 4):
                    log("sync.dryrun.item", trace=trace, account_id=aid, idx=i)
            else:
                # 次ステップで実装: token refresh -> list media -> download -> insert ...
                pass
        except Exception as e:
            status = "failed"
            stats["failed"] = 1
            log("sync.account.error", trace=trace, account_id=aid, error=str(e))
            overall_failed += 1
        finally:
            # ジョブ終了
            with eng.begin() as conn:
                conn.execute(
                    text("UPDATE job_sync SET finished_at=UTC_TIMESTAMP(), status=:st, stats_json=:js "
                         "WHERE account_id=:aid AND id=:jid"),
                    {"st": status, "js": json_dumps(stats), "aid": aid, "jid": job_id}
                )
        log("sync.account.end", trace=trace, account_id=aid, status=status, stats=stats)

    if overall_failed:
        log("sync.done", trace=trace, result="partial")
        return 1
    log("sync.done", trace=trace, result="success")
    return 0


def json_dumps(d: Dict[str, Any]) -> str:
    import json
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))
