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
async def api_picker_session_summary(
    picker_session_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """数値 ID でピッカーセッションの選択件数・ジョブ概要を返す。"""
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService

    ps = db.get(PickerSession, picker_session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    return PickerSessionService.session_summary(ps)


@router.post("/session/{session_id:path}/callback")
async def api_picker_session_callback(
    session_id: str,
    body: dict = {},
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """Google Photos Picker のコールバック（選択されたメディア ID）を処理する。"""
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
    page: Optional[int] = Query(None, ge=1),
    pageSize: int = Query(200, ge=1, le=500),
    cursor: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    status_filters: Optional[list[str]] = Query(None, alias="status"),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ピッカーセッションの選択アイテム一覧を返す。"""
    from shared.application.pagination import PaginationParams
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService
    from bounded_contexts.picker_import.infrastructure.picker_session import PickerSession

    if session_id.isdigit():
        ps = db.get(PickerSession, int(session_id))
    else:
        ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    params = PaginationParams(
        page=page,
        page_size=pageSize,
        cursor=cursor,
        use_cursor=cursor is not None or page is None,
    )

    normalized_status_filters: list[str] = []
    for raw_value in status_filters or []:
        if not raw_value:
            continue
        parts = [part.strip().lower() for part in raw_value.split(",") if part.strip()]
        normalized_status_filters.extend(parts)

    search_term = search.strip() if isinstance(search, str) else None

    return PickerSessionService.selection_details(
        ps,
        params,
        status_filters=normalized_status_filters or None,
        search_term=search_term or None,
    )


@router.get("/session/{session_id}/selections/{selection_id:int}/error")
async def api_picker_session_selection_error(
    session_id: str,
    selection_id: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """選択アイテム単体のエラー詳細を返す。"""
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    payload = PickerSessionService.selection_error_payload(ps, selection_id)
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    return payload


@router.post("/session/mediaItems")
async def api_picker_session_media_items(
    body: dict,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """Google Photos Picker から選択済みメディアを取得・保存して取り込みを開始する。"""
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService
    from bounded_contexts.picker_import.application.session_import_logs import log_import_request_error
    from shared.kernel.database.db import db as scoped_db

    session_id = body.get("sessionId") or body.get("session_id") or body.get("pickerSessionId")
    if not session_id or not isinstance(session_id, str):
        raise HTTPException(status_code=400, detail={"error": "invalid_session"})

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    cursor = body.get("cursor") or body.get("pageToken")
    try:
        payload, status_code = PickerSessionService.media_items(ps.session_id, cursor)
    except Exception as exc:
        logger.exception("Picker mediaItems fetch failed for session %s", session_id)
        # セッション詳細画面のログにも残す（session_id 紐付け）。ログ失敗が
        # レスポンス（502）を 500 に変えないよう防御的に扱う。
        try:
            scoped_db.session.rollback()
            resolved_ps = PickerSessionService.resolve_session_identifier(session_id)
            log_import_request_error(
                session_identifier=getattr(resolved_ps, "session_id", session_id),
                session_db_id=getattr(resolved_ps, "id", None),
                event="import.picker.media_items_error",
                message="メディアアイテムの取得に失敗しました",
                exc=exc,
            )
        except Exception:  # pragma: no cover - ログ失敗はレスポンスに影響させない
            logger.exception("Failed to persist media_items error to session log")
        raise HTTPException(
            status_code=502,
            detail={"error": "picker_error", "message": str(exc)},
        )

    if status_code not in (200, 201):
        headers = None
        if status_code == 429 and isinstance(payload, dict):
            retry_after = payload.get("retryAfter")
            if isinstance(retry_after, (int, float)):
                headers = {"Retry-After": str(max(0, int(round(retry_after))))}
        raise HTTPException(status_code=status_code, detail=payload, headers=headers)
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
    limit: Optional[str] = Query(None),
    pageSize: Optional[str] = Query(None),
    cursor: Optional[int] = Query(None),
    after: Optional[int] = Query(None),
    since: Optional[int] = Query(None),
    file_task_id: Optional[str] = Query(None),
    fileTaskId: Optional[str] = Query(None),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ピッカーセッションの取り込みログ（WorkerLog）を返す。"""
    from bounded_contexts.picker_import.application.picker_session_service import (
        PickerSessionService,
        SESSION_LOG_DEFAULT_LIMIT,
        SESSION_LOG_MAX_LIMIT,
    )
    from bounded_contexts.picker_import.application.session_import_logs import (
        collect_local_import_logs,
    )

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    limit_param = limit if limit is not None else pageSize
    limit_value: Optional[int]
    if limit_param is None or not limit_param.strip():
        limit_value = SESSION_LOG_DEFAULT_LIMIT
    elif limit_param.strip().lower() in {"all", "full"}:
        limit_value = None
    else:
        try:
            limit_candidate = int(limit_param)
        except (TypeError, ValueError):
            limit_candidate = None
        if limit_candidate is None:
            limit_value = SESSION_LOG_DEFAULT_LIMIT
        else:
            limit_value = max(1, min(limit_candidate, SESSION_LOG_MAX_LIMIT))

    requested_file_task_id = (file_task_id or fileTaskId or "").strip() or None
    after_value = after if after is not None else since

    file_task_id_index: dict[str, int] = {}
    logs, meta = collect_local_import_logs(
        ps,
        limit=limit_value,
        file_task_id=requested_file_task_id,
        file_task_id_index=file_task_id_index,
        before_log_id=cursor,
        after_log_id=after_value,
        return_meta=True,
    )

    ordered_file_task_ids = sorted(file_task_id_index.items(), key=lambda item: item[1])
    payload = {
        "logs": logs,
        "fileTaskIds": [item[0] for item in ordered_file_task_ids],
        "hasNext": bool(meta.get("has_more")),
        "nextCursor": meta.get("next_cursor"),
        "oldestLogId": meta.get("oldest_log_id"),
        "newestLogId": meta.get("newest_log_id"),
    }
    if requested_file_task_id:
        payload["selectedFileTaskId"] = requested_file_task_id
    return payload


@router.get("/session/{session_id:path}")
async def api_picker_session_status(
    session_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """セッション ID 文字列でピッカーセッションの状態を返す。

    ``{session_id:path}`` は ``/session/`` 以下をすべて受けるため、
    より具体的なルート（selections / logs 等）より必ず後に登録する。
    """
    from bounded_contexts.picker_import.application.picker_session_service import PickerSessionService

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"error": "not_found"})

    return PickerSessionService.status(ps)
