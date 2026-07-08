"""Picker セッション API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/picker_session.py`` を移植。
Google Photos Picker セッションの作成・管理・インポート処理。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/picker", tags=["picker-session"])


def _iso(value) -> Optional[str]:
    if not value:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _serialize_picker_session(ps, db: Session) -> dict[str, Any]:
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession
    from bounded_contexts.photonest.infrastructure.photo_models import PickerSelection
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService

    selection_counts = (
        db.query(PickerSelection.status, func.count(PickerSelection.id).label("count"))
        .filter(PickerSelection.session_id == ps.id)
        .group_by(PickerSelection.status)
        .all()
    )
    raw_counts = {row[0]: row[1] for row in selection_counts}
    counts = PickerSessionService._normalize_selection_counts(raw_counts)

    if ps.selected_count not in (None, 0) or not counts:
        selected_count = ps.selected_count or 0
    else:
        selected_count = sum(counts.values())

    display_status = ps.status
    if ps.status in ("processing", "importing", "error", "failed"):
        normalized = PickerSessionService._determine_completion_status(counts)
        if normalized:
            display_status = normalized

    account = getattr(ps, "account", None)

    return {
        "id": ps.id,
        "sessionId": ps.session_id,
        "accountId": ps.account_id,
        "status": display_status,
        "selectedCount": selected_count,
        "createdAt": _iso(ps.created_at),
        "lastProgressAt": _iso(ps.last_progress_at),
        "counts": counts,
        "accountEmail": getattr(account, "email", None),
        "isLocalImport": ps.account_id is None,
        "trigger": ps.trigger,
        "triggeredByUserId": ps.triggered_by_user_id,
    }


@router.get("/sessions")
async def api_picker_sessions_list(
    page: int = Query(1, ge=1),
    pageSize: int = Query(200, ge=1, le=1000),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """すべての picker セッションのページネーション一覧を返す。"""
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession

    query = db.query(PickerSession)
    total = query.count()
    sessions_rows = (
        query.order_by(PickerSession.created_at.desc())
        .offset((page - 1) * pageSize)
        .limit(pageSize)
        .all()
    )
    items = [_serialize_picker_session(ps, db) for ps in sessions_rows]
    total_pages = (total + pageSize - 1) // pageSize if pageSize else 0

    return {
        "sessions": items,
        "pagination": {
            "hasNext": page < total_pages,
            "hasPrev": page > 1,
            "currentPage": page,
            "totalPages": total_pages,
            "totalCount": total,
        },
        "server_time": _iso(datetime.now(timezone.utc)),
    }


@router.post("/session")
async def api_picker_session_create(
    body: dict = {},
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """Google Photos Picker セッションを作成する。"""
    from shared.infrastructure.models.google_account import GoogleAccount
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService

    account_id = body.get("account_id")

    if account_id is None:
        account = db.query(GoogleAccount).filter_by(status="active").first()
        if not account:
            raise HTTPException(status_code=400, detail={"error": "invalid_account"})
        account_id = account.id
    else:
        if not isinstance(account_id, int):
            raise HTTPException(status_code=400, detail={"error": "invalid_account"})
        account = db.query(GoogleAccount).filter_by(id=account_id, status="active").first()
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    logger.info("picker session create begin: account_id=%s", account_id)
    payload, status_code = PickerSessionService.create(
        account,
        triggered_by_user_id=int(principal.user_id),
    )
    if status_code != 200:
        # サービスからの詳細エラーは内部ログのみ、クライアントには汎用メッセージを返す
        logger.warning("Picker session create failed: status=%s payload=%s", status_code, payload)
        raise HTTPException(
            status_code=status_code,
            detail={"error": payload.get("error") if isinstance(payload, dict) and "error" in payload else "picker_session_create_failed"},
        )
    # 成功ペイロードにはサービスから返されたデータを直接使用（picker URL 等を含む）
    # ただし内部エラーフィールドは除外する
    if isinstance(payload, dict):
        payload.pop("traceback", None)
        payload.pop("exception", None)
    return payload


@router.get("/session/{picker_session_id:int}")
async def api_picker_session_get_by_id(
    picker_session_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """数値 ID でピッカーセッション詳細を返す。"""
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService

    ps = db.get(PickerSession, picker_session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    payload = PickerSessionService.serialize_session_detail(ps, db)
    return {"session": payload}


@router.get("/session/{session_id:path}")
async def api_picker_session_get(
    session_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """セッション ID 文字列でピッカーセッション詳細を返す。"""
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    payload = PickerSessionService.serialize_session_detail(ps, db)
    return {"session": payload}


@router.post("/session/{session_id:path}/callback")
async def api_picker_session_callback(
    session_id: str,
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """Google Photos Picker のコールバックを処理する。"""
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    payload, status_code = PickerSessionService.handle_callback(ps, body)
    if status_code not in (200, 201):
        raise HTTPException(status_code=status_code, detail=payload)
    return payload


@router.get("/session/{session_id}/selections")
async def api_picker_session_selections(
    session_id: str,
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=500),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ピッカーセッションの選択アイテム一覧を返す。"""
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession
    from bounded_contexts.photonest.infrastructure.photo_models import PickerSelection

    if session_id.isdigit():
        ps = db.get(PickerSession, int(session_id))
    else:
        ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    selections_query = db.query(PickerSelection).filter(PickerSelection.session_id == ps.id)
    total = selections_query.count()
    rows = selections_query.order_by(PickerSelection.id.asc()).offset((page - 1) * pageSize).limit(pageSize).all()

    items = [PickerSessionService.serialize_selection(sel) for sel in rows]
    total_pages = (total + pageSize - 1) // pageSize if pageSize else 0
    return {
        "items": items,
        "pagination": {
            "currentPage": page,
            "pageSize": pageSize,
            "totalCount": total,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrev": page > 1,
        },
    }


@router.post("/session/mediaItems")
async def api_picker_session_media_items(
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """Google Photos からメディアアイテムを取得する。"""
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService

    session_id = body.get("session_id") or body.get("pickerSessionId")
    if not session_id:
        raise HTTPException(status_code=400, detail={"error": "session_id_required"})

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    page_token = body.get("pageToken")
    payload, status_code = PickerSessionService.get_media_items(ps, page_token=page_token)
    if status_code not in (200, 201):
        raise HTTPException(status_code=status_code, detail=payload)
    return payload


@router.post("/session/{session_id:path}/import")
async def api_picker_session_import(
    session_id: str,
    body: dict = {},
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ピッカーセッションのインポートタスクをキューに投入する。"""
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService

    if session_id.isdigit():
        raise HTTPException(
            status_code=400,
            detail={"error": "numeric_ids_not_supported", "message": "Use session_id hash instead"},
        )

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    account_id_in = body.get("account_id")
    try:
        payload, status_code = PickerSessionService.enqueue_import(ps, account_id_in)
    except Exception as exc:
        logger.exception("Import request error for session %s", session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_server_error", "message": "インポートの開始に失敗しました"},
        )

    if status_code not in (200, 201):
        raise HTTPException(status_code=status_code, detail=payload)
    return payload


@router.post("/session/{picker_session_id:int}/finish")
async def api_picker_session_finish(
    picker_session_id: int,
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ピッカーセッションを完了状態にする。"""
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService

    final_status = body.get("status")
    if final_status not in {"imported", "expired", "error"}:
        raise HTTPException(status_code=400, detail={"error": "invalid_status"})

    ps = db.get(PickerSession, picker_session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    payload, status_code = PickerSessionService.finish(ps, final_status)
    if status_code not in (200, 201):
        raise HTTPException(status_code=status_code, detail=payload)
    return payload


@router.get("/session/{session_id}/logs")
async def api_picker_session_logs(
    session_id: str,
    limit: int = Query(100, ge=1, le=1000),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ピッカーセッションのログを返す。"""
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    logs = PickerSessionService.get_session_logs(ps, limit=limit)
    return {"logs": logs, "session_id": session_id}
