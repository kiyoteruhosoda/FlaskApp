"""同期・変換ジョブ履歴 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/routes_sync_jobs.py`` を移植。
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

router = APIRouter(prefix="/sync", tags=["sync-jobs"])

_STATS_SUMMARY_KEYS = (
    "total", "processed", "success", "skipped",
    "failed", "canceled", "pending", "duplicate",
)
_VALID_STATUSES = {"queued", "running", "success", "partial", "failed", "canceled"}


def _iso(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_json(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _stats_summary(stats: dict[str, Any]) -> dict[str, Any]:
    return {key: stats[key] for key in _STATS_SUMMARY_KEYS if key in stats}


def _duration_ms(job) -> Optional[int]:
    if not job.started_at or not job.finished_at:
        return None
    delta = job.finished_at - job.started_at
    return int(delta.total_seconds() * 1000)


def categorize_target(target: Optional[str], task_name: Optional[str] = None) -> str:
    needle = f"{target or ''} {task_name or ''}".lower()
    if "local_import" in needle:
        return "local_import"
    if "picker" in needle:
        return "picker_import"
    if "transcode" in needle or "playback" in needle:
        return "transcode"
    if "thumb" in needle:
        return "thumbnail"
    if "google" in needle or "oauth" in needle:
        return "google_photos"
    return "other"


def _serialize_job(job, *, detailed: bool = False) -> dict[str, Any]:
    celery_task = job.celery_task
    stats = _parse_json(job.stats_json)
    payload: dict[str, Any] = {
        "id": job.id,
        "target": job.target,
        "targetCategory": categorize_target(job.target, job.task_name),
        "taskName": job.task_name or None,
        "queueName": job.queue_name,
        "trigger": job.trigger,
        "status": job.status,
        "accountId": job.account_id,
        "sessionId": job.session_id,
        "celeryTaskId": job.celery_task_id,
        "startedAt": _iso(job.started_at),
        "finishedAt": _iso(job.finished_at),
        "durationMs": _duration_ms(job),
        "statsSummary": _stats_summary(stats),
        "errorMessage": getattr(celery_task, "error_message", None),
        "retryable": job.status in ("failed", "partial"),
    }
    if detailed:
        payload["stats"] = stats
        payload["args"] = _parse_json(job.args_json)
        if celery_task is not None:
            payload["celeryTask"] = {
                "taskName": celery_task.task_name,
                "status": getattr(celery_task.status, "value", str(celery_task.status)),
                "errorMessage": celery_task.error_message,
                "startedAt": _iso(celery_task.started_at),
                "finishedAt": _iso(celery_task.finished_at),
            }
    return payload


@router.get("/jobs")
async def api_sync_jobs_list(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=500),
    status_filter: str | None = Query(None, alias="status"),
    target: str | None = Query(None),
    since: str | None = Query(None),
    until: str | None = Query(None),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """同期・変換ジョブの履歴一覧を返す。"""
    from shared.infrastructure.models.job_sync import JobSync
    from shared.infrastructure.models.celery_task import CeleryTaskRecord  # noqa: F401

    query = db.query(JobSync)

    if status_filter and status_filter in _VALID_STATUSES:
        query = query.filter(JobSync.status == status_filter)

    since_dt = _parse_dt(since)
    if since_dt is not None:
        query = query.filter(JobSync.started_at >= since_dt)
    until_dt = _parse_dt(until)
    if until_dt is not None:
        query = query.filter(JobSync.started_at <= until_dt)

    if target:
        like_map = {
            "local_import": "%local_import%",
            "picker_import": "%picker%",
            "transcode": "%transcode%",
            "thumbnail": "%thumb%",
            "google_photos": "%google%",
        }
        pattern = like_map.get(target)
        if pattern is not None:
            query = query.filter(JobSync.target.ilike(pattern))

    ordered = query.order_by(
        JobSync.started_at.is_(None), JobSync.started_at.desc(), JobSync.id.desc()
    )

    if target:
        all_rows = ordered.all()
        filtered = [j for j in all_rows if categorize_target(j.target, j.task_name) == target]
        total = len(filtered)
        start = (page - 1) * pageSize
        rows = filtered[start: start + pageSize]
    else:
        total = query.count()
        rows = ordered.offset((page - 1) * pageSize).limit(pageSize).all()

    jobs = [_serialize_job(job) for job in rows]
    total_pages = math.ceil(total / pageSize) if pageSize else 0

    return {
        "jobs": jobs,
        "pagination": {
            "currentPage": page,
            "pageSize": pageSize,
            "totalCount": total,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrev": page > 1,
        },
        "filter": {
            "status": status_filter,
            "target": target,
            "since": _iso(since_dt),
            "until": _iso(until_dt),
        },
        "server_time": _iso(datetime.now(timezone.utc)),
    }


@router.get("/jobs/{job_id}")
async def api_sync_job_detail(
    job_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """単一ジョブの詳細を返す。"""
    from shared.infrastructure.models.job_sync import JobSync

    job = db.get(JobSync, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job not found", "id": job_id},
        )
    return {"job": _serialize_job(job, detailed=True), "server_time": _iso(datetime.now(timezone.utc))}


@router.post("/jobs/{job_id}/retry")
async def api_sync_job_retry(
    job_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """失敗/部分成功ジョブを再実行する。"""
    from shared.infrastructure.models.job_sync import JobSync

    job = db.get(JobSync, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job not found", "id": job_id},
        )
    if job.status not in ("failed", "partial"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "job is not retryable", "status": job.status, "id": job_id},
        )
    if not job.task_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "job has no task name to retry", "id": job_id},
        )

    call = _parse_json(job.args_json)
    args = call.get("args") if isinstance(call.get("args"), list) else []
    kwargs = call.get("kwargs") if isinstance(call.get("kwargs"), dict) else {}

    try:
        from cli.src.celery.celery_app import celery
        result = celery.send_task(job.task_name, args=list(args), kwargs=dict(kwargs))
        task_id = getattr(result, "id", None)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "failed to dispatch retry", "detail": str(exc)},
        )

    new_job = JobSync(
        target=job.target,
        task_name=job.task_name,
        queue_name=job.queue_name,
        trigger="retry",
        account_id=job.account_id,
        session_id=job.session_id,
        status="queued",
        args_json=job.args_json,
    )
    db.add(new_job)
    db.commit()

    return {
        "success": True,
        "retriedFrom": job_id,
        "newJobId": new_job.id,
        "taskId": task_id,
        "server_time": _iso(datetime.now(timezone.utc)),
    }
