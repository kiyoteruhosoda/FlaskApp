from datetime import datetime, timezone
import json
from flask import (
    Blueprint, current_app, jsonify, request, session
)
from flask_login import login_required
from sqlalchemy import func
from ..extensions import db
from core.models.google_account import GoogleAccount
from core.models.picker_session import PickerSession
from core.models.job_sync import JobSync
from core.models.photo_models import PickerSelection
from .picker_session_service import (
    PickerSessionService,
    _get_lock as _get_media_items_lock,
    _release_lock as _release_media_items_lock,
    time,
)
from core.tasks.picker_import import enqueue_picker_import_item  # re-export for tests

bp = Blueprint('picker_session_api', __name__)

@bp.get("/picker/sessions")
@login_required
def api_picker_sessions_list():
    """Return list of all picker sessions."""
    sessions = PickerSession.query.order_by(PickerSession.created_at.desc()).all()
    result = []
    for ps in sessions:
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
        counts = {status: count for status, count in selection_counts}
        
        result.append({
            "id": ps.id,
            "sessionId": ps.session_id,
            "accountId": ps.account_id,
            "status": ps.status,
            "selectedCount": ps.selected_count or 0,
            "createdAt": ps.created_at.isoformat().replace("+00:00", "Z") if ps.created_at else None,
            "lastProgressAt": ps.last_progress_at.isoformat().replace("+00:00", "Z") if ps.last_progress_at else None,
            "counts": counts
        })
    
    return jsonify({"sessions": result})

@bp.post("/picker/session")
@login_required
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
@login_required
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
@login_required
def api_picker_session_selections(picker_session_id: int):
    """Return detailed picker selection list for a session."""
    ps = PickerSession.query.get(picker_session_id)
    if not ps:
        return jsonify({"error": "not_found"}), 404
    payload = PickerSessionService.selection_details(ps)
    return jsonify(payload)


@bp.get("/picker/session/<path:session_id>/selections")
@login_required
def api_picker_session_selections_by_session_id(session_id: str):
    """Return selection list using external ``session_id`` string.

    Clients may only know the Google Photos Picker ``session_id`` which can be a
    bare UUID or include the ``picker_sessions/`` prefix.  This endpoint
    resolves that identifier and delegates to the integer based handler so that
    behavior remains consistent.
    """
    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return jsonify({"error": "not_found"}), 404
    payload = PickerSessionService.selection_details(ps)
    return jsonify(payload)


@bp.get("/picker/session/<string:session_id>")
@login_required
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


@bp.get("/picker/session/picker_sessions/<string:uuid>")
@login_required
def api_picker_session_status_prefixed(uuid: str):
    """Alias for status that accepts the picker_sessions prefix as a segment."""
    return api_picker_session_status(f"picker_sessions/{uuid}")


@bp.post("/picker/session/mediaItems")
@login_required
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
        return jsonify(payload), status
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
@login_required
def api_picker_session_import(picker_session_id: int):
    """Enqueue import task for picker session.

    The frontend does not pass ``account_id`` in the request body, so the
    parameter is now optional.  If provided it must match the session's
    ``account_id``; otherwise the session's own ``account_id`` is used.
    The picker session status is also updated to ``importing`` so that the
    client can immediately reflect the change in state.
    """
    data = request.get_json(silent=True) or {}
    account_id_in = data.get("account_id")
    ps = PickerSession.query.get(picker_session_id)
    if not ps:
        return jsonify({"error": "not_found"}), 404
    payload, status = PickerSessionService.enqueue_import(ps, account_id_in)
    if status in (409, 500):
        current_app.logger.info(
            json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "picker_session_id": picker_session_id,
                "status": ps.status,
                **({"job_id": payload.get("jobId")} if payload.get("jobId") else {}),
            }),
            extra={"event": "picker.import.suppress"},
        )
    else:
        current_app.logger.info(
            json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "picker_session_id": picker_session_id,
                "job_id": payload.get("jobId"),
                "job_status": payload.get("status"),
                "celery_task_id": payload.get("celeryTaskId"),
            }),
            extra={"event": "picker.import.enqueue"},
        )
    return jsonify(payload), status


@bp.post("/picker/session/<path:session_id>/import")
@login_required
def api_picker_session_import_by_session_id(session_id: str):
    """Enqueue import task using external ``session_id``.

    Some clients only know the Google Photos Picker ``session_id`` (which may
    include a slash like ``picker_sessions/<uuid>``). This endpoint resolves the
    corresponding internal picker session and delegates to the integer-based
    import handler to keep behavior identical.
    """
    ps = PickerSessionService.resolve_session_identifier(session_id)
    if not ps:
        return jsonify({"error": "not_found"}), 404
    # Delegate to the primary import implementation
    return api_picker_session_import(ps.id)


@bp.post("/picker/session/<int:picker_session_id>/finish")
@login_required
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
