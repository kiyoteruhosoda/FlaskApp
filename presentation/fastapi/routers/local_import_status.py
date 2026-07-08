"""Local Import状態管理 FastAPI ルーター。

Flask版 ``bounded_contexts/photonest/presentation/local_import_status_api.py`` を移植。
app.py では ``/api`` プレフィックスで登録する → 最終的に ``/api/local-import/...``
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/local-import", tags=["local-import-status"])


# ---------------------------------------------------------------------------
# エンドポイント
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/status")
async def get_session_status(
    session_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession

    session = db.get(PickerSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"error": f"セッションが見つかりません: {session_id}"})

    stats = session.stats()
    return {
        "session_id": session_id,
        "state": session.status,
        "stats": stats,
        "last_updated": session.updated_at.isoformat(),
        "created_at": session.created_at.isoformat(),
    }


@router.get("/sessions/{session_id}/errors")
async def get_session_errors(
    session_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    from bounded_contexts.photonest.infrastructure.local_import.audit_log_repository import AuditLogRepository

    repo = AuditLogRepository(db)
    errors = repo.get_errors(session_id=session_id, limit=100)
    return {
        "session_id": session_id,
        "total_count": len(errors),
        "errors": [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "message": log.message,
                "error_type": log.error_type,
                "error_message": log.error_message,
                "recommended_actions": log.recommended_actions or [],
                "item_id": log.item_id,
                "details": log.details,
            }
            for log in errors
        ],
    }


@router.get("/sessions/{session_id}/items")
async def get_session_items(
    session_id: int,
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession
    from bounded_contexts.photonest.infrastructure.photo_models import PickerSelection

    session = db.get(PickerSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"error": f"セッションが見つかりません: {session_id}"})

    status_counts = dict(
        db.query(
            PickerSelection.status,
            func.count(PickerSelection.id),
        )
        .filter(PickerSelection.session_id == session_id)
        .group_by(PickerSelection.status)
        .all()
    )
    total = sum(status_counts.values())

    query = db.query(PickerSelection).filter(PickerSelection.session_id == session_id)
    if status:
        query = query.filter(PickerSelection.status == status)

    selections = query.order_by(PickerSelection.id).limit(limit).offset(offset).all()

    def _iso(value):
        return value.isoformat() if value else None

    items = [
        {
            "id": sel.id,
            "item_id": str(sel.id),
            "filename": sel.local_filename,
            "file_path": sel.local_file_path,
            "status": sel.status,
            "attempts": sel.attempts,
            "error_msg": sel.error_msg,
            "google_media_id": sel.google_media_id,
            "enqueued_at": _iso(sel.enqueued_at),
            "started_at": _iso(sel.started_at),
            "finished_at": _iso(sel.finished_at),
        }
        for sel in selections
    ]

    return {
        "session_id": session_id,
        "total_count": total,
        "status_counts": status_counts,
        "filter": {"status": status, "limit": limit, "offset": offset},
        "returned_count": len(items),
        "items": items,
    }


@router.get("/sessions/{session_id}/transitions")
async def get_state_transitions(
    session_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    from bounded_contexts.photonest.infrastructure.local_import.audit_log_repository import AuditLogRepository

    repo = AuditLogRepository(db)
    transitions = repo.get_state_transitions(session_id)
    return {
        "session_id": session_id,
        "total_count": len(transitions),
        "transitions": [
            {
                "timestamp": log.timestamp.isoformat(),
                "from_state": log.from_state,
                "to_state": log.to_state,
                "reason": log.details.get("reason") if log.details else None,
                "item_id": log.item_id,
            }
            for log in transitions
        ],
    }


@router.get("/sessions/{session_id}/consistency-check")
async def check_consistency(
    session_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    from bounded_contexts.photonest.infrastructure.local_import.state_repositories import (
        create_state_management_service,
    )

    try:
        state_mgr, _ = create_state_management_service(db)
        result = state_mgr.validate_consistency(session_id)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"error": f"整合性チェックに失敗: {str(exc)}"})


@router.get("/sessions/{session_id}/troubleshooting")
async def get_troubleshooting_report(
    session_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession
    from bounded_contexts.photonest.infrastructure.local_import.audit_log_repository import AuditLogRepository
    from bounded_contexts.photonest.application.local_import.troubleshooting import generate_troubleshooting_report

    session = db.get(PickerSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail={"error": f"セッションが見つかりません: {session_id}"})

    repo = AuditLogRepository(db)
    errors = repo.get_errors(session_id=session_id, limit=100)
    stats = session.stats()

    report = generate_troubleshooting_report(
        session_id=session_id,
        session_state=session.status,
        errors=[log.to_dict() for log in errors],
        stats=stats,
    )
    return report


@router.get("/sessions/{session_id}/performance")
async def get_performance_metrics(
    session_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    from bounded_contexts.photonest.infrastructure.local_import.audit_log_repository import AuditLogRepository

    repo = AuditLogRepository(db)
    metrics = repo.get_performance_metrics(session_id)

    total_duration = sum(log.duration_ms for log in metrics if log.duration_ms)
    avg_duration = total_duration / len(metrics) if metrics else 0

    return {
        "session_id": session_id,
        "total_operations": len(metrics),
        "total_duration_ms": total_duration,
        "avg_duration_ms": avg_duration,
        "metrics": [
            {
                "timestamp": log.timestamp.isoformat(),
                "operation_name": log.details.get("operation_name") if log.details else None,
                "duration_ms": log.duration_ms,
                "file_size_bytes": log.details.get("file_size_bytes") if log.details else None,
                "throughput_mbps": log.details.get("throughput_mbps") if log.details else None,
            }
            for log in metrics
        ],
    }


@router.get("/sessions/{session_id}/logs")
async def get_all_logs(
    session_id: int,
    category: str | None = Query(None),
    level: str | None = Query(None),
    limit: int = Query(100, ge=1),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    from bounded_contexts.photonest.infrastructure.local_import.audit_log_repository import (
        AuditLogRepository,
        LogCategory,
        LogLevel,
    )

    repo = AuditLogRepository(db)
    log_category = LogCategory(category) if category else None
    log_level = LogLevel(level) if level else None

    logs = repo.get_by_session(
        session_id=session_id,
        limit=limit,
        level=log_level,
        category=log_category,
    )
    return {
        "session_id": session_id,
        "total_count": len(logs),
        "filters": {
            "category": category,
            "level": level,
            "limit": limit,
        },
        "logs": [log.to_dict() for log in logs],
    }


@router.get("/items/{item_id}/logs")
async def get_item_logs(
    item_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    from bounded_contexts.photonest.infrastructure.local_import.audit_log_repository import AuditLogRepository

    repo = AuditLogRepository(db)
    logs = repo.get_by_item(item_id, limit=50)
    return {
        "item_id": item_id,
        "total_count": len(logs),
        "logs": [log.to_dict() for log in logs],
    }


__all__ = ["router"]
