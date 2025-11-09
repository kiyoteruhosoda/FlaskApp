from datetime import datetime, timezone
import io
import json
import zipfile
from typing import Any, Dict, Optional, List
from flask import (
    current_app,
    jsonify,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import login_required
from sqlalchemy import func, or_
from ..extensions import db
from core.models.google_account import GoogleAccount
from core.models.picker_session import PickerSession
from core.models.job_sync import JobSync
from core.models.photo_models import PickerSelection
from core.models.worker_log import WorkerLog
from .picker_session_service import (
    PickerSessionService,
    _get_lock as _get_media_items_lock,
    _release_lock as _release_media_items_lock,
    time,
)
from core.tasks.picker_import import enqueue_picker_import_item  # re-export for tests
from .pagination import PaginationParams, paginate_and_respond
from .routes import login_or_jwt_required  # JWT認証対応のデコレータをインポート
from .concurrency import create_limiter, limit_concurrency
from .openapi import json_request_body
from .blueprint import AuthEnforcedBlueprint

bp = AuthEnforcedBlueprint('picker_session_api', __name__)


def _json_response(payload, status: int = 200):
    response = jsonify(payload)
    if status == 429 and isinstance(payload, dict):
        retry_after = payload.get("retryAfter")
        if isinstance(retry_after, (int, float)):
            seconds = max(0, int(round(retry_after)))
            response.headers["Retry-After"] = str(seconds)
    return response, status


_picker_sessions_list_limiter = create_limiter("PICKER_SESSIONS_LIST")
_picker_session_create_limiter = create_limiter("PICKER_SESSION_CREATE")
_picker_session_callback_limiter = create_limiter("PICKER_SESSION_CALLBACK")
_picker_session_summary_limiter = create_limiter("PICKER_SESSION_SUMMARY")
_picker_session_selections_limiter = create_limiter("PICKER_SESSION_SELECTIONS")
_picker_session_selections_external_limiter = create_limiter(
    "PICKER_SESSION_SELECTIONS_BY_SESSION"
)
_picker_session_selection_error_limiter = create_limiter(
    "PICKER_SESSION_SELECTION_ERROR"
)
_picker_session_status_limiter = create_limiter("PICKER_SESSION_STATUS")
_picker_session_logs_limiter = create_limiter("PICKER_SESSION_LOGS")
_picker_session_logs_download_limiter = create_limiter(
    "PICKER_SESSION_LOGS_DOWNLOAD"
)
_picker_session_logs_prefixed_limiter = create_limiter(
    "PICKER_SESSION_LOGS_PREFIX"
)
_picker_session_status_prefixed_limiter = create_limiter(
    "PICKER_SESSION_STATUS_PREFIX"
)
_picker_session_file_tasks_limiter = create_limiter(
    "PICKER_SESSION_FILE_TASKS"
)
_picker_session_import_numeric_limiter = create_limiter(
    "PICKER_SESSION_IMPORT_NUMERIC"
)
_picker_session_import_limiter = create_limiter("PICKER_SESSION_IMPORT")
_picker_session_finish_limiter = create_limiter("PICKER_SESSION_FINISH")


_LOG_SESSION_KEYS = {
    "session_id",
    "sessionId",
    "session_identifier",
    "sessionIdentifier",
    "session_key",
    "sessionKey",
    "session_db_id",
    "active_session_id",
    "target_session_id",
    "import_session_id",
    "importSessionId",
    "picker_session_id",
    "pickerSessionId",
}

_LOG_NESTED_SESSION_KEYS = {"session_id", "sessionId", "session_key", "sessionKey", "id"}


def _normalize_log_identifier(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    if isinstance(value, (int,)):
        return str(value)
    return None


def _extract_session_identifier_candidates(mapping: Any) -> set[str]:
    candidates: set[str] = set()
    if not isinstance(mapping, dict):
        return candidates

    for key in _LOG_SESSION_KEYS:
        if key in mapping:
            normalized = _normalize_log_identifier(mapping.get(key))
            if normalized:
                candidates.add(normalized)

    session_block = mapping.get("session")
    if isinstance(session_block, dict):
        for key in _LOG_NESTED_SESSION_KEYS:
            normalized = _normalize_log_identifier(session_block.get(key))
            if normalized:
                candidates.add(normalized)

    result_block = mapping.get("result")
    if isinstance(result_block, dict):
        candidates.update(_extract_session_identifier_candidates(result_block))

    details_block = mapping.get("details")
    if isinstance(details_block, dict):
        candidates.update(_extract_session_identifier_candidates(details_block))

    return candidates


def _build_session_aliases(ps) -> set[str]:
    session_aliases: set[str] = set()
    if not ps:
        return session_aliases

    session_identifier = getattr(ps, "session_id", None)

    def _add_alias(value: Any) -> None:
        normalized = _normalize_log_identifier(value)
        if normalized:
            session_aliases.add(normalized)

    _add_alias(session_identifier)

    if session_identifier:
        base_identifier = session_identifier.split("#", 1)[0]
        _add_alias(base_identifier)
        if "/" in base_identifier:
            _add_alias(base_identifier.split("/", 1)[-1])

    account_id = getattr(ps, "account_id", None)
    if account_id is not None:
        _add_alias(f"google-{account_id}")

    db_id = getattr(ps, "id", None)
    if db_id is not None:
        _add_alias(db_id)

    return session_aliases

@bp.get("/picker/sessions")
@login_or_jwt_required
@limit_concurrency(_picker_sessions_list_limiter)
def api_picker_sessions_list():
    """Return paginated list of all picker sessions."""
    
    # ページングパラメータの取得
    params = PaginationParams.from_request(default_page_size=200)
    
    # ベースクエリの構築
    query = PickerSession.query
    
    # セッションアイテムのシリアライザ関数
    def serialize_picker_session(ps):
        # 各セッションの選択数を集計
        selection_counts = (
            db.session.query(
                PickerSelection.status,
                func.count(PickerSelection.id).label('count')
            )
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
        is_local_import = ps.account_id is None

        return {
            "id": ps.id,
            "sessionId": ps.session_id,
            "accountId": ps.account_id,
            "status": display_status,
            "selectedCount": selected_count,
            "createdAt": ps.created_at.isoformat().replace("+00:00", "Z") if ps.created_at else None,
            "lastProgressAt": ps.last_progress_at.isoformat().replace("+00:00", "Z") if ps.last_progress_at else None,
            "counts": counts,
            "accountEmail": getattr(account, "email", None),
            "isLocalImport": is_local_import
        }
    
    # ページング処理
    result = paginate_and_respond(
        query=query,
        params=params,
        serializer_func=serialize_picker_session,
        id_column=PickerSession.id,
        created_at_column=PickerSession.created_at,
        count_total=not params.use_cursor,  # カーソルベースでない場合のみ総件数カウント
        default_page_size=200
    )
    
    # レスポンス形式を既存のAPIと合わせるため、sessionsキーで包む
    return _json_response({
        "sessions": result["items"],
        "pagination": {
            "hasNext": result["hasNext"],
            "hasPrev": result["hasPrev"],
            "nextCursor": result.get("nextCursor"),
            "prevCursor": result.get("prevCursor"),
            "currentPage": result.get("currentPage"),
            "totalPages": result.get("totalPages"),
            "totalCount": result.get("totalCount")
        },
        "server_time": result.get("server_time")
    })

@bp.post("/picker/session")
@login_or_jwt_required
@limit_concurrency(_picker_session_create_limiter)
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Create a picker session for selecting Google Photos items.",
        required=False,
        schema={
            "type": "object",
            "properties": {
                "account_id": {
                    "type": "integer",
                    "description": "Specific Google account id to use for the picker.",
                },
                "title": {
                    "type": "string",
                    "description": "Optional dialog title shown to the user.",
                },
            },
            "additionalProperties": False,
        },
        example={"account_id": 1, "title": "Select media"},
    ),
)
def api_picker_session_create():
    """Create a Google Photos Picker session."""
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    title = data.get("title") or "Select from Google Photos"

    if account_id is None:
        account = GoogleAccount.query.filter_by(status="active").first()
        if not account:
            return _json_response({"error": "invalid_account"}, 400)
        account_id = account.id
    else:
        if not isinstance(account_id, int):
            return _json_response({"error": "invalid_account"}, 400)
        account = GoogleAccount.query.filter_by(id=account_id, status="active").first()
        if not account:
            return _json_response({"error": "not_found"}, 404)

    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "account_id": account_id,
            }
        ),
        extra={"event": "picker.create.begin"}
    )

    # Delegate to service
    payload, status = PickerSessionService.create(account, title)
    if status != 200:
        current_app.logger.exception(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "account_id": account_id,
                    "message": payload.get("message") if isinstance(payload, dict) else None,
                }
            ),
            extra={"event": "picker.create.fail"}
        )
        return _json_response(payload, status)

    session["picker_session_id"] = payload.get("pickerSessionId")
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "account_id": account_id,
                "picker_session_id": payload.get("pickerSessionId"),
            }
        ),
        extra={"event": "picker.create.success"}
    )
    return _json_response(payload)


@bp.post("/picker/session/<path:session_id>/callback")
@login_or_jwt_required
@limit_concurrency(_picker_session_callback_limiter)
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Receive selected media identifiers from the Google Photos Picker.",
        schema={
            "type": "object",
            "properties": {
                "mediaItemIds": {
                    "description": "List of Google Photos media item ids that were selected.",
                    "oneOf": [
                        {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        {"type": "string"},
                    ],
                }
            },
            "additionalProperties": False,
        },
        example={"mediaItemIds": ["ABCD123", "EFGH456"]},
    ),
)
def api_picker_session_callback(session_id):
    """Receive selected media item IDs from Google Photos Picker."""
    ps = PickerSession.query.filter_by(session_id=session_id).first()
    if not ps:
        return _json_response({"error": "not_found"}, 404)
    data = request.get_json(silent=True) or {}
    ids = data.get("mediaItemIds") or []
    if isinstance(ids, str):
        ids = [ids]
    count = sum(1 for mid in ids if isinstance(mid, str))
    ps.selected_count = (ps.selected_count or 0) + count
    ps.status = "ready"
    ps.last_progress_at = datetime.now(timezone.utc)
    if count > 0:
        ps.media_items_set = True
    db.session.commit()
    return _json_response({"result": "ok", "count": count})


@bp.get("/picker/session/<int:picker_session_id>")
@login_or_jwt_required
@limit_concurrency(_picker_session_summary_limiter)
def api_picker_session_summary(picker_session_id):
    """Return selection counts and job summary for picker session."""
    ps = PickerSession.query.get(picker_session_id)
    if not ps:
        return _json_response({"error": "not_found"}, 404)

    counts = dict(
        db.session.query(
            PickerSelection.status, func.count(PickerSelection.id)
        )
        .filter(PickerSelection.session_id == ps.id)
        .group_by(PickerSelection.status)
        .all()
    )

    job = (
        JobSync.query.filter_by(target="picker_import", session_id=ps.id)
        .order_by(JobSync.started_at.is_(None), JobSync.started_at.desc())
        .first()
    )
    job_summary = None
    if job:
        job_summary = {
            "id": job.id,
            "status": job.status,
            "startedAt": job.started_at.isoformat().replace("+00:00", "Z") if job.started_at else None,
            "finishedAt": job.finished_at.isoformat().replace("+00:00", "Z") if job.finished_at else None,
        }

    return _json_response({"countsByStatus": counts, "jobSync": job_summary})


@bp.get("/picker/session/<int:picker_session_id>/selections")
@login_or_jwt_required
@limit_concurrency(_picker_session_selections_limiter)
def api_picker_session_selections(picker_session_id: int):
    """Return detailed picker selection list for a session (DEPRECATED: Use session_id instead)."""
    # セキュリティ改善：数値IDの使用を拒否
    return _json_response({"error": "numeric_ids_not_supported", "message": "Use session_id hash instead"}, 400)


@bp.get("/picker/session/<path:session_id>/selections")
@login_or_jwt_required
@limit_concurrency(_picker_session_selections_external_limiter)
def api_picker_session_selections_by_session_id(session_id: str):
    """Return paginated selection list using external ``session_id`` string.

    Clients may only know the Google Photos Picker ``session_id`` which can be a
    bare UUID or include the ``picker_sessions/`` prefix.  This endpoint
    resolves that identifier and delegates to the integer based handler so that
    behavior remains consistent.
    """
    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return _json_response({"error": "not_found"}, 404)
    
    # ページングパラメータの取得
    params = PaginationParams.from_request(default_page_size=200)

    raw_status_filters = request.args.getlist("status")
    status_filters = []
    for raw_value in raw_status_filters:
        if not raw_value:
            continue
        parts = [part.strip().lower() for part in raw_value.split(",") if part.strip()]
        status_filters.extend(parts)

    search_term = request.args.get("search", type=str)
    if isinstance(search_term, str):
        search_term = search_term.strip()
        if not search_term:
            search_term = None

    payload = PickerSessionService.selection_details(
        ps,
        params,
        status_filters=status_filters or None,
        search_term=search_term,
    )

    selections = payload.get("selections", [])
    for item in selections:
        item_id = item.get("id")
        status = (item.get("status") or "").lower()
        if not item_id:
            continue
        if status not in {"failed", "expired"} and not item.get("error"):
            continue
        item["errorDetailsUrl"] = url_for(
            "photo_view.selection_error_detail",
            session_id=ps.session_id,
            selection_id=item_id,
        )

    return _json_response(payload)


@bp.get("/picker/session/<path:session_id>/selections/<int:selection_id>/error")
@login_or_jwt_required
@limit_concurrency(_picker_session_selection_error_limiter)
def api_picker_session_selection_error(session_id: str, selection_id: int):
    """Return error detail payload for a single picker selection."""

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return _json_response({"error": "not_found"}, 404)

    payload = PickerSessionService.selection_error_payload(ps, selection_id)
    if not payload:
        return _json_response({"error": "not_found"}, 404)

    return _json_response(payload)


@bp.get("/picker/session/<string:session_id>")
@login_or_jwt_required
@limit_concurrency(_picker_session_status_limiter)
def api_picker_session_status(session_id):
    """Return status of a picker session."""
    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return _json_response({"error": "not_found"}, 404)
    payload = PickerSessionService.status(ps)
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
                "status": payload.get("status"),
            }
        ),
        extra={"event": "picker.status.get"}
    )
    return _json_response(payload)


def _collect_local_import_logs(
    ps,
    limit=None,
    include_raw: bool = False,
    file_task_id: Optional[str] = None,
    file_task_id_index: Optional[Dict[str, int]] = None,
):
    """Collect import logs for a picker session.

    Args:
        ps: Picker session model instance.
        limit: Optional number of log entries to return. ``None`` returns all
            matching entries.
        include_raw: When ``True`` the original log payloads and metadata are
            included in the response dictionaries.
        file_task_id: Optional identifier to scope logs to a single processed file.
        file_task_id_index: Optional mapping updated with the first log ID for
            each encountered ``file_task_id``.

    Returns:
        List of log dictionaries sorted by ID ascending.
    """

    if not ps:
        return []

    session_aliases = _build_session_aliases(ps)
    account_identifier = None
    if getattr(ps, "account_id", None) is not None:
        account_identifier = _normalize_log_identifier(ps.account_id)

    query = WorkerLog.query.filter(
        or_(WorkerLog.event.like("local_import%"), WorkerLog.event.like("import.%"))
    )

    if file_task_id:
        query = query.filter(WorkerLog.file_task_id == file_task_id)

    bounded_limit: Optional[int] = None

    if limit is None:
        query = query.order_by(WorkerLog.id.asc())
    else:
        scan_multiplier = 5 if file_task_id_index is None else 10
        bounded_limit = max(limit * scan_multiplier, limit)
        if file_task_id_index is None:
            query = query.order_by(WorkerLog.id.desc()).limit(bounded_limit)
        else:
            query = query.order_by(WorkerLog.id.asc()).limit(bounded_limit)

    def _transform_row(row):
        try:
            payload = json.loads(row.message)
        except Exception:
            payload = {"message": row.message}

        if not isinstance(payload, dict):
            payload = {"message": payload}

        extras: Dict[str, Any] = {}
        payload_extras = payload.get("_extra")
        if isinstance(payload_extras, dict):
            extras.update(payload_extras)

        row_extras = row.extra_json if isinstance(row.extra_json, dict) else None
        if row_extras:
            extras.update(row_extras)

        def _coerce_progress_step(value: Any) -> Optional[int]:
            if value is None:
                return None
            if isinstance(value, bool):
                return None
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                candidate = value.strip()
                if not candidate:
                    return None
                try:
                    return int(candidate)
                except ValueError:
                    return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        progress_step = row.progress_step
        if progress_step is None:
            for candidate in (
                extras.get("progress_step"),
                extras.get("progressStep"),
                payload.get("progress_step"),
                payload.get("progressStep"),
            ):
                progress_step = _coerce_progress_step(candidate)
                if progress_step is not None:
                    break

        candidate_values = set()
        candidate_values.update(_extract_session_identifier_candidates(extras))
        candidate_values.update(_extract_session_identifier_candidates(payload))

        session_matches = bool(session_aliases.intersection(candidate_values))

        if not session_matches and account_identifier is not None:
            for container in (extras, payload):
                if not isinstance(container, dict):
                    continue
                account_value = _normalize_log_identifier(
                    container.get("account_id") or container.get("accountId")
                )
                if account_value != account_identifier:
                    continue

                source_value = container.get("import_source") or container.get("source")
                if isinstance(source_value, str) and source_value.lower().startswith("google"):
                    session_matches = True
                    break

        if not session_matches:
            return None

        excluded_keys = {
            "session_id",
            "session_db_id",
            "active_session_id",
            "target_session_id",
            "status",
            "progress_step",
            "progressStep",
        }

        details = {
            key: value
            for key, value in extras.items()
            if key not in excluded_keys
        }

        status_value = row.status or payload.get("status") or extras.get("status")

        if status_value is not None and not isinstance(status_value, str):
            try:
                status_value = str(status_value)
            except Exception:
                status_value = None

        message = payload.get("message")
        if not isinstance(message, str):
            try:
                message = json.dumps(message, ensure_ascii=False, default=str)
            except Exception:
                message = str(message)

        log_entry = {
            "id": row.id,
            "createdAt": row.created_at.isoformat().replace("+00:00", "Z")
            if row.created_at
            else None,
            "level": row.level,
            "event": row.event,
            "status": status_value,
            "message": message,
            "details": details,
        }

        if row.file_task_id:
            log_entry["fileTaskId"] = row.file_task_id

        if progress_step is not None:
            log_entry["progressStep"] = progress_step

        if include_raw:
            log_entry["raw"] = {
                "id": row.id,
                "created_at": row.created_at.isoformat().replace("+00:00", "Z")
                if row.created_at
                else None,
                "level": row.level,
                "event": row.event,
                "status": row.status,
                "logger_name": row.logger_name,
                "task_name": row.task_name,
                "task_uuid": row.task_uuid,
                "worker_hostname": row.worker_hostname,
                "queue_name": row.queue_name,
                "file_task_id": row.file_task_id,
                "progress_step": row.progress_step
                if row.progress_step is not None
                else progress_step,
                "raw_message": row.message,
                "parsed_message": payload,
                "extra_json": row.extra_json,
                "meta_json": row.meta_json,
                "trace": row.trace,
            }

        return log_entry

    logs: list[Dict[str, Any]] = []
    tracked_file_task_ids: set[str] = set()
    extracted_present = False

    for row in query:
        log_entry = _transform_row(row)
        if log_entry is None:
            continue

        if file_task_id_index is not None and row.file_task_id:
            file_task_id_index.setdefault(row.file_task_id, row.id)

        file_task_id_value = log_entry.get("fileTaskId")
        if isinstance(file_task_id_value, str):
            tracked_file_task_ids.add(file_task_id_value)

        if limit is not None and len(logs) >= limit:
            if file_task_id_index is None:
                break
            if tracked_file_task_ids and tracked_file_task_ids.issubset(
                file_task_id_index.keys()
            ):
                break
            continue

        logs.append(log_entry)
        if log_entry.get("event") == "local_import.zip.extracted":
            extracted_present = True

    if limit is not None:
        logs.sort(key=lambda item: item.get("id", 0))

        if not extracted_present:
            fallback_query = WorkerLog.query.filter(
                WorkerLog.event == "local_import.zip.extracted"
            )
            if file_task_id:
                fallback_query = fallback_query.filter(WorkerLog.file_task_id == file_task_id)
            fallback_query = fallback_query.order_by(WorkerLog.id.asc())
            if bounded_limit is not None:
                fallback_query = fallback_query.limit(bounded_limit)

            fallback_entry = None
            for row in fallback_query:
                entry = _transform_row(row)
                if entry is None:
                    continue
                if file_task_id_index is not None and row.file_task_id:
                    file_task_id_index.setdefault(row.file_task_id, row.id)
                fallback_entry = entry

            if fallback_entry and fallback_entry.get("id") not in {
                item.get("id") for item in logs
            }:
                logs.append(fallback_entry)
                logs.sort(key=lambda item: item.get("id", 0))
                if len(logs) > limit:
                    if limit == 1:
                        logs = [fallback_entry]
                    else:
                        trimmed = [
                            item
                            for item in logs
                            if item.get("id") != fallback_entry.get("id")
                        ]
                        trimmed = trimmed[-(limit - 1) :]
                        trimmed.append(fallback_entry)
                        trimmed.sort(key=lambda item: item.get("id", 0))
                        logs = trimmed

    return logs


def _normalize_file_task_state(
    progress_step: Optional[int],
    status: Optional[str],
    level: Optional[str],
    event: Optional[str],
) -> str:
    normalized_level = (level or "").upper()
    if normalized_level in {"ERROR", "CRITICAL"}:
        return "error"

    normalized_status = (status or "").strip().lower()
    normalized_event = (event or "").strip().lower()

    if normalized_status:
        if any(keyword in normalized_status for keyword in ("error", "fail", "missing", "denied", "timeout")):
            return "error"
        if "skip" in normalized_status:
            return "skipped"
        if normalized_status.startswith("dup") or "duplicate" in normalized_status:
            return "duplicate"
        if normalized_status in {"warning", "canceled", "cancelled"}:
            return "warning"
        if normalized_status in {"success", "completed", "done"}:
            return "success"
        if normalized_status in {"stored", "copied", "written"}:
            return "storing"
        if "thumbnail" in normalized_status:
            return "thumbnail"
        if any(keyword in normalized_status for keyword in ("meta", "analy")):
            return "metadata"
        if normalized_status in {"processing", "running", "pending"}:
            return "processing"

    if normalized_event:
        if "error" in normalized_event or "failed" in normalized_event:
            return "error"
        if "duplicate" in normalized_event:
            return "duplicate"
        if "skip" in normalized_event:
            return "skipped"
        if "thumbnail" in normalized_event:
            return "thumbnail"
        if any(keyword in normalized_event for keyword in ("meta", "analy")):
            return "metadata"
        if normalized_event.endswith(".success") or normalized_event.endswith(".done"):
            return "success"
        if any(keyword in normalized_event for keyword in ("cleanup", "store", "copy")):
            return "storing"

    if isinstance(progress_step, int):
        if progress_step >= 9:
            return "error"
        if progress_step >= 5:
            return "success"
        if progress_step == 4:
            return "storing"
        if progress_step == 3:
            return "thumbnail"
        if progress_step == 2:
            return "metadata"
        if progress_step == 1:
            return "processing"

    return "processing"


def _collect_local_import_file_tasks(
    ps,
    *,
    limit: Optional[int] = None,
) -> tuple[List[Dict[str, Any]], int]:
    if not ps:
        return [], 0

    logs = _collect_local_import_logs(ps, limit=None)
    summary: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for entry in logs:
        file_task_id = entry.get("fileTaskId")
        if not file_task_id:
            continue

        current = summary.get(file_task_id)
        if current is None:
            current = {
                "fileTaskId": file_task_id,
                "state": "processing",
            }
            summary[file_task_id] = current
            order.append(file_task_id)

        details = entry.get("details") or {}

        display_name: Optional[str] = None
        for key in (
            "basename",
            "file",
            "filename",
            "name",
            "path",
            "file_path",
            "source",
            "source_path",
        ):
            value = details.get(key)
            if isinstance(value, str):
                candidate = value.strip()
                if candidate:
                    display_name = candidate
                    break
        if display_name:
            current["fileName"] = display_name

        status_text = entry.get("status") or details.get("status")
        if status_text:
            current["status"] = str(status_text)

        progress_step = entry.get("progressStep")
        progress_int: Optional[int]
        if progress_step is None:
            progress_int = None
        elif isinstance(progress_step, int):
            progress_int = progress_step
        else:
            try:
                progress_int = int(progress_step)
            except (TypeError, ValueError):
                progress_int = None
        if progress_int is not None:
            current["progressStep"] = progress_int

        message = entry.get("message")
        if message:
            current["message"] = message

        event = entry.get("event")
        if event:
            current["event"] = event

        level = entry.get("level")
        if level:
            current["level"] = level

        updated_at = entry.get("createdAt")
        if updated_at:
            current["updatedAt"] = updated_at

        note_value = details.get("notes") or details.get("reason")
        if note_value:
            current["notes"] = str(note_value)

        error_value = details.get("error") or details.get("error_message")
        if error_value:
            current["error"] = str(error_value)

        current["state"] = _normalize_file_task_state(
            current.get("progressStep"),
            current.get("status"),
            current.get("level"),
            current.get("event"),
        )

    items: List[Dict[str, Any]] = [summary[file_id] for file_id in order]

    for item in items:
        if not item.get("fileName"):
            item["fileName"] = item["fileTaskId"]
        for key in list(item.keys()):
            if item[key] is None:
                item.pop(key)

    items.sort(key=lambda item: item.get("updatedAt") or "", reverse=True)
    total_count = len(items)

    if limit is not None and total_count > 0:
        bounded = max(1, min(limit, total_count))
        items = items[:bounded]

    return items, total_count


@bp.get("/picker/session/<string:session_id>/logs")
@login_or_jwt_required
@limit_concurrency(_picker_session_logs_limiter)
def api_picker_session_logs(session_id: str):
    """Return recent local import logs for a picker session."""

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return _json_response({"error": "not_found"}, 404)

    limit = request.args.get("limit", type=int) or 100
    limit = max(1, min(limit, 500))

    requested_file_task_id = request.args.get("file_task_id") or request.args.get(
        "fileTaskId"
    )
    if isinstance(requested_file_task_id, str):
        requested_file_task_id = requested_file_task_id.strip() or None

    file_task_id_index: Dict[str, int] = {}

    logs = _collect_local_import_logs(
        ps,
        limit=limit,
        file_task_id=requested_file_task_id,
        file_task_id_index=file_task_id_index,
    )

    ordered_file_task_ids = sorted(file_task_id_index.items(), key=lambda item: item[1])
    file_task_ids = [item[0] for item in ordered_file_task_ids]

    payload = {"logs": logs, "fileTaskIds": file_task_ids}
    if requested_file_task_id:
        payload["selectedFileTaskId"] = requested_file_task_id

    return _json_response(payload)


@bp.get("/picker/session/<string:session_id>/file-tasks")
@login_or_jwt_required
@limit_concurrency(_picker_session_file_tasks_limiter)
def api_picker_session_file_tasks(session_id: str):
    """Return latest worker log derived file task summaries."""

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return _json_response({"error": "not_found"}, 404)

    limit = request.args.get("limit", type=int)
    if limit is not None:
        limit = max(1, min(limit, 1000))

    items, total = _collect_local_import_file_tasks(ps, limit=limit)

    return _json_response({"items": items, "total": total})


@bp.get("/picker/session/<string:session_id>/logs/download")
@login_or_jwt_required
@limit_concurrency(_picker_session_logs_download_limiter)
def api_picker_session_logs_download(session_id: str):
    """Download the complete local import logs for a picker session as a ZIP."""

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return _json_response({"error": "not_found"}, 404)

    requested_file_task_id = request.args.get("file_task_id") or request.args.get(
        "fileTaskId"
    )
    if isinstance(requested_file_task_id, str):
        requested_file_task_id = requested_file_task_id.strip() or None

    logs = _collect_local_import_logs(
        ps,
        limit=None,
        include_raw=True,
        file_task_id=requested_file_task_id,
    )

    log_lines = []
    for entry in logs:
        log_lines.append(json.dumps(entry, ensure_ascii=False, sort_keys=True))

    metadata = {
        "session_id": ps.session_id,
        "session_db_id": ps.id,
        "downloaded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "log_count": len(logs),
    }

    if requested_file_task_id:
        metadata["file_task_id"] = requested_file_task_id

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("logs.jsonl", "\n".join(log_lines) + ("\n" if log_lines else ""))
        archive.writestr(
            "metadata.json",
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
        )

    buffer.seek(0)

    session_identifier = ps.session_id or "session"
    safe_name = [
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in session_identifier
    ]
    filename = "{}{}".format("".join(safe_name).strip("._") or "session", "_logs.zip")

    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
    )


@bp.get("/picker/session/picker_sessions/<string:uuid>/logs")
@login_or_jwt_required
@limit_concurrency(_picker_session_logs_prefixed_limiter)
def api_picker_session_logs_prefixed(uuid: str):
    """Alias for logs endpoint that accepts picker_sessions prefix."""

    return api_picker_session_logs(f"picker_sessions/{uuid}")


@bp.get("/picker/session/picker_sessions/<string:uuid>")
@login_or_jwt_required
@limit_concurrency(_picker_session_status_prefixed_limiter)
def api_picker_session_status_prefixed(uuid: str):
    """Alias for status that accepts the picker_sessions prefix as a segment."""
    return api_picker_session_status(f"picker_sessions/{uuid}")


@bp.post("/picker/session/mediaItems")
@login_or_jwt_required
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Fetch the next page of media items for a picker session.",
        schema={
            "type": "object",
            "properties": {
                "sessionId": {
                    "type": "string",
                    "description": "Picker session identifier returned from /picker/session.",
                },
                "cursor": {
                    "type": "string",
                    "description": "Opaque pagination cursor from a previous response.",
                },
            },
            "required": ["sessionId"],
            "additionalProperties": False,
        },
        example={"sessionId": "picker_sessions/abc123", "cursor": "page-token"},
    ),
)
def api_picker_session_media_items():
    """Fetch selected media items from Google Photos Picker and store them."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("sessionId")
    if not session_id or not isinstance(session_id, str):
        return _json_response({"error": "invalid_session"}, 400)
    cursor = data.get("cursor")
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
                "cursor": cursor,
            }
        ),
        extra={"event": "picker.mediaItems.begin"},
    )
    try:
        payload, status = PickerSessionService.media_items(session_id, cursor)
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "session_id": session_id,
                    "saved": payload.get("saved"),
                    "duplicates": payload.get("duplicates"),
                    "status": status,
                }
            ),
            extra={"event": "picker.mediaItems.success"},
        )
        return _json_response(payload, status)
    except Exception as e:
        current_app.logger.error(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "session_id": session_id,
                    "error": str(e),
                }
            ),
            extra={"event": "picker.mediaItems.fail"}
        )
        return _json_response({"error": "picker_error", "message": str(e)}, 502)


@bp.post("/picker/session/<int:picker_session_id>/import")
@login_or_jwt_required
@limit_concurrency(_picker_session_import_numeric_limiter)
def api_picker_session_import(picker_session_id: int):
    """Enqueue import task for picker session (DEPRECATED: Use session_id instead)."""
    # セキュリティ改善：数値IDの使用を拒否
    return _json_response({"error": "numeric_ids_not_supported", "message": "Use session_id hash instead"}, 400)


@bp.post("/picker/session/<path:session_id>/import")
@login_or_jwt_required
@limit_concurrency(_picker_session_import_limiter)
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Enqueue the import job for the given picker session.",
        required=False,
        schema={
            "type": "object",
            "properties": {
                "account_id": {
                    "type": "integer",
                    "description": "Optional override for the Google account that will perform the import.",
                }
            },
            "additionalProperties": False,
        },
        example={"account_id": 42},
    ),
)
def api_picker_session_import_by_session_id(session_id: str):
    """Enqueue import task using external ``session_id``.

    Some clients only know the Google Photos Picker ``session_id`` (which may
    include a slash like ``picker_sessions/<uuid>``). This endpoint resolves the
    corresponding internal picker session and processes the import directly.
    """
    # 数値のみの場合は拒否（セキュリティ改善）
    if session_id.isdigit():
        return _json_response({"error": "numeric_ids_not_supported", "message": "Use session_id hash instead"}, 400)
    
    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return _json_response({"error": "not_found"}, 404)
    
    # 直接インポート処理を実行
    data = request.get_json(silent=True) or {}
    account_id_in = data.get("account_id")
    payload, status = PickerSessionService.enqueue_import(ps, account_id_in)
    
    if status in (409, 500):
        current_app.logger.info(
            json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "picker_session_id": ps.id,
                "session_id": session_id,
                "status": ps.status,
                **({"job_id": payload.get("jobId")} if payload.get("jobId") else {}),
            }),
            extra={"event": "import.picker.suppress"},
        )
    else:
        current_app.logger.info(
            json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "picker_session_id": ps.id,
                "session_id": session_id,
                "job_id": payload.get("jobId"),
                "job_status": payload.get("status"),
                "celery_task_id": payload.get("celeryTaskId"),
            }),
            extra={"event": "import.picker.enqueue"},
        )
    return _json_response(payload, status)


@bp.post("/picker/session/<int:picker_session_id>/finish")
@login_or_jwt_required
@limit_concurrency(_picker_session_finish_limiter)
@bp.doc(
    methods=["POST"],
    requestBody=json_request_body(
        "Mark the picker session as finished with the specified status.",
        schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["imported", "expired", "error"],
                    "description": "Final state of the picker session.",
                }
            },
            "required": ["status"],
            "additionalProperties": False,
        },
        example={"status": "imported"},
    ),
)
def api_picker_session_finish(picker_session_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in {"imported", "expired", "error"}:
        return _json_response({"error": "invalid_status"}, 400)

    ps = PickerSession.query.get(picker_session_id)
    if not ps:
        return _json_response({"error": "not_found"}, 404)

    payload, status_code = PickerSessionService.finish(ps, status)
    return _json_response(payload, status_code)
