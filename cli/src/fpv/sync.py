from __future__ import annotations
from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.orm import Session

from .db import get_engine_from_env
from .logs import log, new_trace_id
from .config import PhotoNestConfig
from . import google
from core.models.google_account import GoogleAccount
from core.models.job_sync import JobSync


def run_sync(all_accounts: bool = True,
             account_id: Optional[int] = None,
             dry_run: bool = True) -> int:
    """
    Returns: exit code (0=success, 1=partial/failed)
    """
    trace = new_trace_id()
    eng = get_engine_from_env()
    cfg = PhotoNestConfig.from_env()

    # アカウント抽出 (ORM)
    with Session(eng) as session:
        query = session.query(GoogleAccount).filter(GoogleAccount.status == "active")
        if not all_accounts and account_id is not None:
            query = query.filter(GoogleAccount.id == account_id)
        accounts: List[GoogleAccount] = query.all()

    if not accounts:
        log("sync.no_accounts", trace=trace)
        return 0

    overall_failed = 0

    for acc in accounts:
        aid, email, token_json = int(acc.id), acc.email, acc.oauth_token_json
        log("sync.account.begin", trace=trace, account_id=aid, email=email, dry_run=dry_run)

        # ジョブ開始 (ORM)
        with Session(eng) as session:
            job = JobSync(target="google_photos", account_id=aid, status="running")
            session.add(job)
            session.commit()
            job_id = job.id

        # ダミー処理（dry-run）: 3件処理した体で統計を出す
        stats: Dict[str, Any] = {"listed": 0, "new": 0, "dup": 0, "failed": 0}
        status = "success"

        try:
            if dry_run:
                for i in range(1, 4):
                    log("sync.dryrun.item", trace=trace, account_id=aid, idx=i)
                stats["listed"] = 3
            else:
                token, meta = google.refresh_access_token(
                    token_json, cfg.oauth_key, cfg.google_client_id, cfg.google_client_secret
                )
                log(
                    "sync.token.ok",
                    trace=trace,
                    account_id=aid,
                    expires_in=meta.get("expires_in", 0),
                )
                page = google.list_media_items_once(token, page_size=100)
                items = page.get("mediaItems") or []
                stats["listed"] = len(items)
                log(
                    "sync.list.ok",
                    trace=trace,
                    account_id=aid,
                    listed=len(items),
                    nextPageToken=bool(page.get("nextPageToken")),
                )
        except google.ReauthRequired as e:
            status = "failed"
            overall_failed += 1
            stats["failed"] += 1
            log(
                "sync.account.reauth_required",
                trace=trace,
                account_id=aid,
                error=str(e),
            )
        except Exception as e:
            status = "failed"
            overall_failed += 1
            stats["failed"] += 1
            log("sync.account.error", trace=trace, account_id=aid, error=str(e))
        finally:
            with Session(eng) as session:
                job = session.get(JobSync, job_id)
                if job:
                    job.finished_at = datetime.utcnow()
                    job.status = status
                    job.stats_json = json_dumps(stats)
                    session.commit()
        log("sync.account.end", trace=trace, account_id=aid, status=status, stats=stats)

    if overall_failed:
        log("sync.done", trace=trace, result="partial")
        return 1
    log("sync.done", trace=trace, result="success")
    return 0


def json_dumps(d: Dict[str, Any]) -> str:
    import json
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))
