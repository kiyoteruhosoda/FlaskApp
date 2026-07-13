"""DBログ閲覧 API（FastAPI）。

``log``（APIリクエスト単位・requestId で追跡）と ``worker_log``（Celery ジョブ
単位・taskId で追跡）の内容を、時間範囲・ログレベル等でフィルタして一覧返却する。
閲覧専用（書き込みAPIは提供しない）。`admin:system-settings` 権限が必要。
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

router = APIRouter(prefix="/admin/logs", tags=["admin:logs"])

_SOURCES = ("app", "worker")

# 一覧表示でのメッセージ最大長（全文・traceback は詳細APIで返す）
_LIST_MESSAGE_MAX = 500


def _require_log_view_permission(principal: AuthenticatedPrincipal) -> None:
    if not principal.can("admin:system-settings"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "forbidden",
                "message": "admin:system-settings permission required",
            },
        )


def _iso(value: Optional[datetime]) -> Optional[str]:
    if not value:
        return None
    if value.tzinfo is None:
        # DB には naive UTC で保存されている
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _parse_dt_utc_naive(raw: Optional[str]) -> Optional[datetime]:
    """ISO 8601 文字列を DB 保存形式（naive UTC）の datetime に変換する。"""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _truncate_message(message: Optional[str]) -> tuple[str, bool]:
    text = message or ""
    if len(text) > _LIST_MESSAGE_MAX:
        return text[:_LIST_MESSAGE_MAX], True
    return text, False


def _serialize_app_log(row, *, detailed: bool = False) -> dict[str, Any]:
    message, truncated = _truncate_message(row.message)
    payload: dict[str, Any] = {
        "id": row.id,
        "source": "app",
        "createdAt": _iso(row.created_at),
        "level": row.level,
        "event": row.event,
        "message": row.message if detailed else message,
        "messageTruncated": False if detailed else truncated,
        "path": row.path,
        "requestId": row.request_id,
        "hasTrace": bool(row.trace),
    }
    if detailed:
        payload["trace"] = row.trace
    return payload


def _serialize_worker_log(row, *, detailed: bool = False) -> dict[str, Any]:
    message, truncated = _truncate_message(row.message)
    payload: dict[str, Any] = {
        "id": row.id,
        "source": "worker",
        "createdAt": _iso(row.created_at),
        "level": row.level,
        "event": row.event,
        "message": row.message if detailed else message,
        "messageTruncated": False if detailed else truncated,
        "taskName": row.task_name,
        "taskUuid": row.task_uuid,
        "fileTaskId": row.file_task_id,
        "status": row.status,
        "workerHostname": row.worker_hostname,
        "queueName": row.queue_name,
        "loggerName": row.logger_name,
        "hasTrace": bool(row.trace),
    }
    if detailed:
        payload["trace"] = row.trace
        payload["meta"] = row.meta_json
        payload["extra"] = row.extra_json
    return payload


def _log_model(source: str):
    if source == "app":
        from shared.infrastructure.models.log import Log

        return Log
    from shared.infrastructure.models.worker_log import WorkerLog

    return WorkerLog


@router.get("")
async def list_logs(
    source: str = Query("app", description="ログの出所（app=APIリクエスト / worker=Celery ジョブ）"),
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    level: str | None = Query(None, description="ログレベル（カンマ区切りで複数指定可・大文字小文字無視）"),
    event: str | None = Query(None, description="イベント名（部分一致）"),
    q: str | None = Query(None, description="メッセージ本文（部分一致）"),
    traceId: str | None = Query(
        None,
        description="追跡キー（app: requestId 完全一致 / worker: taskUuid または fileTaskId 完全一致）",
    ),
    since: str | None = Query(None, description="この日時以降（ISO 8601）"),
    until: str | None = Query(None, description="この日時以前（ISO 8601）"),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """DBに記録されたログを新しい順に一覧で返す（時間・レベル等でフィルタ可能）。"""
    _require_log_view_permission(principal)

    if source not in _SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_source", "message": f"source must be one of {_SOURCES}"},
        )

    model = _log_model(source)
    query = db.query(model)

    levels = [part.strip().upper() for part in (level or "").split(",") if part.strip()]
    if levels:
        query = query.filter(func.upper(model.level).in_(levels))

    if event:
        query = query.filter(model.event.ilike(f"%{event}%"))

    if q:
        query = query.filter(model.message.ilike(f"%{q}%"))

    if traceId:
        if source == "app":
            query = query.filter(model.request_id == traceId)
        else:
            query = query.filter(
                (model.task_uuid == traceId) | (model.file_task_id == traceId)
            )

    since_dt = _parse_dt_utc_naive(since)
    if since_dt is not None:
        query = query.filter(model.created_at >= since_dt)
    until_dt = _parse_dt_utc_naive(until)
    if until_dt is not None:
        query = query.filter(model.created_at <= until_dt)

    total = query.count()
    rows = (
        query.order_by(model.created_at.desc(), model.id.desc())
        .offset((page - 1) * pageSize)
        .limit(pageSize)
        .all()
    )

    serialize = _serialize_app_log if source == "app" else _serialize_worker_log
    logs = [serialize(row) for row in rows]
    total_pages = math.ceil(total / pageSize) if pageSize else 0

    # レベルフィルタの選択肢（実際に記録されている値から作る）
    available_levels = sorted(
        {value for (value,) in db.query(model.level).distinct().all() if value}
    )

    return {
        "logs": logs,
        "pagination": {
            "currentPage": page,
            "pageSize": pageSize,
            "totalCount": total,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrev": page > 1,
        },
        "availableLevels": available_levels,
        "filter": {
            "source": source,
            "level": levels or None,
            "event": event,
            "q": q,
            "traceId": traceId,
            "since": _iso(since_dt),
            "until": _iso(until_dt),
        },
        "server_time": _iso(datetime.now(timezone.utc)),
    }


@router.get("/{source}/{log_id}")
async def get_log_detail(
    source: str,
    log_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ログ1件の詳細（メッセージ全文・traceback 含む）を返す。"""
    _require_log_view_permission(principal)

    if source not in _SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_source", "message": f"source must be one of {_SOURCES}"},
        )

    model = _log_model(source)
    row = db.get(model, log_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "log_not_found"},
        )

    serialize = _serialize_app_log if source == "app" else _serialize_worker_log
    return {"log": serialize(row, detailed=True)}
