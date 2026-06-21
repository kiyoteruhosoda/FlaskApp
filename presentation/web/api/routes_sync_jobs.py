"""同期・変換ジョブ履歴 API (`/api/sync/jobs`).

要件 §18.10「同期ジョブ履歴」のデータ源として、Celery 実行ごとに記録される
:class:`JobSync` を一覧/詳細で返す。target は生の Celery タスク名のため、UI の
フィルタ向けにカテゴリ(`local_import` / `picker_import` / `transcode` / `thumbnail`
/ `google_photos` / `other`)へ正規化して併せて返す。
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import jsonify, request

from core.models.celery_task import CeleryTaskRecord  # noqa: F401 - リレーション解決用
from core.models.job_sync import JobSync

from ..bootstrap.extensions import db
from . import bp
from .routes import login_or_jwt_required


_STATS_SUMMARY_KEYS = (
    "total",
    "processed",
    "success",
    "skipped",
    "failed",
    "canceled",
    "pending",
    "duplicate",
)

_VALID_STATUSES = {"queued", "running", "success", "partial", "failed", "canceled"}


def _iso(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    return value.isoformat().replace("+00:00", "Z")


def categorize_target(target: Optional[str], task_name: Optional[str] = None) -> str:
    """生の target / タスク名を UI フィルタ用カテゴリへ正規化する."""

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


def _parse_json(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _stats_summary(stats: Dict[str, Any]) -> Dict[str, Any]:
    """stats_json から件数系の代表値のみ抽出する(大量データ対策)."""

    summary = {key: stats[key] for key in _STATS_SUMMARY_KEYS if key in stats}
    return summary


def _duration_ms(job: JobSync) -> Optional[int]:
    if not job.started_at or not job.finished_at:
        return None
    delta = job.finished_at - job.started_at
    return int(delta.total_seconds() * 1000)


def _serialize_job(job: JobSync, *, detailed: bool = False) -> Dict[str, Any]:
    celery_task = job.celery_task
    stats = _parse_json(job.stats_json)
    payload: Dict[str, Any] = {
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


@bp.get("/sync/jobs")
@login_or_jwt_required
def api_sync_jobs_list():
    """同期・変換ジョブの履歴一覧を返す.

    Query Parameters:
        page: ページ番号(1始まり, 既定1)
        pageSize: 1ページ件数(既定50, 上限500)
        status: queued/running/success/partial/failed/canceled
        target: カテゴリ(local_import/picker_import/transcode/thumbnail/google_photos)
        since/until: started_at の範囲(ISO 8601)
    """

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(int(request.args.get("pageSize", 50)), 500))
    except (TypeError, ValueError):
        page_size = 50

    query = JobSync.query

    status = request.args.get("status")
    if status and status in _VALID_STATUSES:
        query = query.filter(JobSync.status == status)

    target_category = request.args.get("target")

    since = _parse_dt(request.args.get("since"))
    if since is not None:
        query = query.filter(JobSync.started_at >= since)
    until = _parse_dt(request.args.get("until"))
    if until is not None:
        query = query.filter(JobSync.started_at <= until)

    # target はタスク名からの派生カテゴリのため DB 側で完全一致できない。
    # 代表的なカテゴリは LIKE で絞り込み、残差は Python 側で確定させる。
    if target_category:
        like_map = {
            "local_import": "%local_import%",
            "picker_import": "%picker%",
            "transcode": "%transcode%",
            "thumbnail": "%thumb%",
            "google_photos": "%google%",
        }
        pattern = like_map.get(target_category)
        if pattern is not None:
            query = query.filter(JobSync.target.ilike(pattern))

    ordered = query.order_by(
        JobSync.started_at.is_(None), JobSync.started_at.desc(), JobSync.id.desc()
    )

    if target_category:
        # LIKE 後に Python 側でカテゴリを厳密判定(thumbnail と transcode の取り違え防止)。
        all_rows = ordered.all()
        filtered = [
            job
            for job in all_rows
            if categorize_target(job.target, job.task_name) == target_category
        ]
        total = len(filtered)
        start = (page - 1) * page_size
        rows = filtered[start : start + page_size]
    else:
        total = query.count()
        rows = ordered.offset((page - 1) * page_size).limit(page_size).all()

    jobs = [_serialize_job(job) for job in rows]
    total_pages = math.ceil(total / page_size) if page_size else 0

    return jsonify(
        {
            "jobs": jobs,
            "pagination": {
                "currentPage": page,
                "pageSize": page_size,
                "totalCount": total,
                "totalPages": total_pages,
                "hasNext": page < total_pages,
                "hasPrev": page > 1,
            },
            "filter": {
                "status": status,
                "target": target_category,
                "since": _iso(since),
                "until": _iso(until),
            },
            "server_time": _iso(datetime.now(timezone.utc)),
        }
    )


@bp.get("/sync/jobs/<int:job_id>")
@login_or_jwt_required
def api_sync_job_detail(job_id: int):
    """単一ジョブの詳細(stats_json 全文・args・Celery タスク情報)を返す."""

    job = db.session.get(JobSync, job_id)
    if job is None:
        return jsonify({"error": "job not found", "id": job_id}), 404

    return jsonify(
        {
            "job": _serialize_job(job, detailed=True),
            "server_time": _iso(datetime.now(timezone.utc)),
        }
    )


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
