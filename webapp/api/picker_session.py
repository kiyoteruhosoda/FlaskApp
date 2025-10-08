from datetime import datetime, timezone
import io
import json
import zipfile
from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import login_required
from sqlalchemy import func
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

bp = Blueprint('picker_session_api', __name__)

@bp.get("/picker/sessions")
@login_or_jwt_required
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
    return jsonify({
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
        "serverTime": result.get("serverTime")
    })

@bp.post("/picker/session")
@login_or_jwt_required
def api_picker_session_create():
    """Create a Google Photos Picker session."""
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    title = data.get("title") or "Select from Google Photos"

    if account_id is None:
        account = GoogleAccount.query.filter_by(status="active").first()
        if not account:
            return jsonify({"error": "invalid_account"}), 400
        account_id = account.id
    else:
        if not isinstance(account_id, int):
            return jsonify({"error": "invalid_account"}), 400
        account = GoogleAccount.query.filter_by(id=account_id, status="active").first()
        if not account:
            return jsonify({"error": "not_found"}), 404

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
        return jsonify(payload), status

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
    return jsonify(payload)


@bp.post("/picker/session/<path:session_id>/callback")
def api_picker_session_callback(session_id):
    """Receive selected media item IDs from Google Photos Picker."""
    ps = PickerSession.query.filter_by(session_id=session_id).first()
    if not ps:
        return jsonify({"error": "not_found"}), 404
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
    return jsonify({"result": "ok", "count": count})


@bp.get("/picker/session/<int:picker_session_id>")
@login_or_jwt_required
def api_picker_session_summary(picker_session_id):
    """Return selection counts and job summary for picker session."""
    ps = PickerSession.query.get(picker_session_id)
    if not ps:
        return jsonify({"error": "not_found"}), 404

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

    return jsonify({"countsByStatus": counts, "jobSync": job_summary})


@bp.get("/picker/session/<int:picker_session_id>/selections")
@login_or_jwt_required
def api_picker_session_selections(picker_session_id: int):
    """Return detailed picker selection list for a session (DEPRECATED: Use session_id instead)."""
    # セキュリティ改善：数値IDの使用を拒否
    return jsonify({"error": "numeric_ids_not_supported", "message": "Use session_id hash instead"}), 400


@bp.get("/picker/session/<path:session_id>/selections")
@login_or_jwt_required
def api_picker_session_selections_by_session_id(session_id: str):
    """Return paginated selection list using external ``session_id`` string.

    Clients may only know the Google Photos Picker ``session_id`` which can be a
    bare UUID or include the ``picker_sessions/`` prefix.  This endpoint
    resolves that identifier and delegates to the integer based handler so that
    behavior remains consistent.
    """
    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return jsonify({"error": "not_found"}), 404
    
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

    return jsonify(payload)


@bp.get("/picker/session/<path:session_id>/selections/<int:selection_id>/error")
@login_or_jwt_required
def api_picker_session_selection_error(session_id: str, selection_id: int):
    """Return error detail payload for a single picker selection."""

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return jsonify({"error": "not_found"}), 404

    payload = PickerSessionService.selection_error_payload(ps, selection_id)
    if not payload:
        return jsonify({"error": "not_found"}), 404

    return jsonify(payload)


@bp.get("/picker/session/<string:session_id>")
@login_or_jwt_required
def api_picker_session_status(session_id):
    """Return status of a picker session."""
    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return jsonify({"error": "not_found"}), 404
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
    return jsonify(payload)


def _collect_local_import_logs(ps, limit=None, include_raw: bool = False):
    """Collect local import logs for a picker session.

    Args:
        ps: Picker session model instance.
        limit: Optional number of log entries to return. ``None`` returns all
            matching entries.
        include_raw: When ``True`` the original log payloads and metadata are
            included in the response dictionaries.

    Returns:
        List of log dictionaries sorted by ID ascending.
    """

    if not ps:
        return []

    session_identifier = ps.session_id

    query = WorkerLog.query.filter(WorkerLog.event.like("local_import%"))

    if limit is None:
        query = query.order_by(WorkerLog.id.asc())
    else:
        query = query.order_by(WorkerLog.id.desc()).limit(limit * 5)

    logs = []

    for row in query:
        try:
            payload = json.loads(row.message)
        except Exception:
            payload = {"message": row.message}

        if not isinstance(payload, dict):
            payload = {"message": payload}

        extras = {}
        payload_extras = payload.get("_extra")
        if isinstance(payload_extras, dict):
            extras.update(payload_extras)

        row_extras = row.extra_json if isinstance(row.extra_json, dict) else None
        if row_extras:
            extras.update(row_extras)

        session_matches = False

        if extras.get("session_id") == session_identifier:
            session_matches = True
        elif ps.id is not None and extras.get("session_db_id") == ps.id:
            session_matches = True
        elif extras.get("active_session_id") == session_identifier:
            session_matches = True
        elif extras.get("target_session_id") == session_identifier:
            session_matches = True

        if not session_matches:
            continue

        excluded_keys = {
            "session_id",
            "session_db_id",
            "active_session_id",
            "target_session_id",
            "status",
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
                "raw_message": row.message,
                "parsed_message": payload,
                "extra_json": row.extra_json,
                "meta_json": row.meta_json,
                "trace": row.trace,
            }

        logs.append(log_entry)

        if limit is not None and len(logs) >= limit:
            break

    if limit is not None:
        logs.sort(key=lambda item: item.get("id", 0))

    return logs


@bp.get("/picker/session/<string:session_id>/logs")
@login_or_jwt_required
def api_picker_session_logs(session_id: str):
    """Return recent local import logs for a picker session."""

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return jsonify({"error": "not_found"}), 404

    limit = request.args.get("limit", type=int) or 100
    limit = max(1, min(limit, 500))

    logs = _collect_local_import_logs(ps, limit=limit)

    return jsonify({"logs": logs})


@bp.get("/picker/session/<string:session_id>/logs/download")
@login_or_jwt_required
def api_picker_session_logs_download(session_id: str):
    """Download the complete local import logs for a picker session as a ZIP."""

    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return jsonify({"error": "not_found"}), 404

    logs = _collect_local_import_logs(ps, limit=None, include_raw=True)

    log_lines = []
    for entry in logs:
        log_lines.append(json.dumps(entry, ensure_ascii=False, sort_keys=True))

    metadata = {
        "session_id": ps.session_id,
        "session_db_id": ps.id,
        "downloaded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "log_count": len(logs),
    }

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
def api_picker_session_logs_prefixed(uuid: str):
    """Alias for logs endpoint that accepts picker_sessions prefix."""

    return api_picker_session_logs(f"picker_sessions/{uuid}")


@bp.get("/picker/session/picker_sessions/<string:uuid>")
@login_or_jwt_required
def api_picker_session_status_prefixed(uuid: str):
    """Alias for status that accepts the picker_sessions prefix as a segment."""
    return api_picker_session_status(f"picker_sessions/{uuid}")


@bp.post("/picker/session/mediaItems")
@login_or_jwt_required
def api_picker_session_media_items():
    """Fetch selected media items from Google Photos Picker and store them."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("sessionId")
    if not session_id or not isinstance(session_id, str):
        return jsonify({"error": "invalid_session"}), 400
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
        response = jsonify(payload)
        if status == 429 and isinstance(payload, dict):
            retry_after = payload.get("retryAfter")
            if isinstance(retry_after, (int, float)):
                seconds = max(0, int(round(retry_after)))
                response.headers["Retry-After"] = str(seconds)
        return response, status
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
        return jsonify({"error": "picker_error", "message": str(e)}), 502


@bp.post("/picker/session/<int:picker_session_id>/import")
@login_or_jwt_required
def api_picker_session_import(picker_session_id: int):
    """Enqueue import task for picker session (DEPRECATED: Use session_id instead)."""
    # セキュリティ改善：数値IDの使用を拒否
    return jsonify({"error": "numeric_ids_not_supported", "message": "Use session_id hash instead"}), 400


@bp.post("/picker/session/<path:session_id>/import")
@login_or_jwt_required
def api_picker_session_import_by_session_id(session_id: str):
    """Enqueue import task using external ``session_id``.

    Some clients only know the Google Photos Picker ``session_id`` (which may
    include a slash like ``picker_sessions/<uuid>``). This endpoint resolves the
    corresponding internal picker session and processes the import directly.
    """
    # 数値のみの場合は拒否（セキュリティ改善）
    if session_id.isdigit():
        return jsonify({"error": "numeric_ids_not_supported", "message": "Use session_id hash instead"}), 400
    
    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return jsonify({"error": "not_found"}), 404
    
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
            extra={"event": "picker.import.suppress"},
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
            extra={"event": "picker.import.enqueue"},
        )
    return jsonify(payload), status


@bp.post("/picker/session/<int:picker_session_id>/finish")
@login_or_jwt_required
def api_picker_session_finish(picker_session_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in {"imported", "expired", "error"}:
        return jsonify({"error": "invalid_status"}), 400

    ps = PickerSession.query.get(picker_session_id)
    if not ps:
        return jsonify({"error": "not_found"}), 404

    payload, status_code = PickerSessionService.finish(ps, status)
    return jsonify(payload), status_code
