from datetime import datetime, timezone
import json
import time
from uuid import uuid4
from threading import Lock
from flask import (
    Blueprint, current_app, jsonify, request, session
)
from flask_login import login_required
from ..extensions import db
from core.models.google_account import GoogleAccount
from core.models.picker_session import PickerSession
from core.models.photo_models import (
    PickedMediaItem,
    MediaItem,
    PhotoMetadata,
    VideoMetadata,
)
from core.crypto import decrypt
from ..auth.utils import refresh_google_token, RefreshTokenError, log_requests_and_send

bp = Blueprint('picker_session_api', __name__)


_media_items_locks = {}
_media_items_locks_lock = Lock()


def _get_media_items_lock(session_id):
    with _media_items_locks_lock:
        lock = _media_items_locks.get(session_id)
        if lock is None:
            lock = Lock()
            _media_items_locks[session_id] = lock
        return lock


def _release_media_items_lock(session_id, lock):
    with _media_items_locks_lock:
        if not lock.locked():
            _media_items_locks.pop(session_id, None)


def _update_picker_session_from_data(ps, data):
    """Apply Google Photos Picker session data to the model."""
    ps.session_id = data.get("id")
    ps.picker_uri = data.get("pickerUri")
    expire = data.get("expireTime")
    if expire is not None:
        try:
            ps.expire_time = datetime.fromisoformat(expire.replace("Z", "+00:00"))
        except Exception:
            ps.expire_time = None
    if data.get("pollingConfig"):
        ps.polling_config_json = json.dumps(data.get("pollingConfig"))
    if data.get("pickingConfig"):
        ps.picking_config_json = json.dumps(data.get("pickingConfig"))
    if "mediaItemsSet" in data:
        ps.media_items_set = data.get("mediaItemsSet")
    ps.updated_at = datetime.now(timezone.utc)

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

    try:
        tokens = refresh_google_token(account)
    except RefreshTokenError as e:
        current_app.logger.error(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "account_id": account_id,
                    "error": str(e),
                }
            ),
            extra={"event": "picker.create.fail"}
        )
        status = 502 if e.status_code >= 500 else 401
        return jsonify({"error": str(e)}), status

    access_token = tokens.get("access_token")
    headers = {"Authorization": f"Bearer {access_token}"}
    body = {"title": title}
    try:
        picker_res = log_requests_and_send(
            "POST",
            "https://photospicker.googleapis.com/v1/sessions",
            json_data=body,
            headers=headers,
            timeout=15,
        )
        picker_res.raise_for_status()
        picker_data = picker_res.json()
    except Exception as e:
        current_app.logger.exception(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "account_id": account_id,
                    "message": str(e),
                }
            ),
            extra={"event": "picker.create.fail"}
        )
        return jsonify({"error": "picker_error", "message": str(e)}), 502

    ps = PickerSession(account_id=account.id, status="pending")
    db.session.add(ps)
    _update_picker_session_from_data(ps, picker_data)
    db.session.commit()
    session["picker_session_id"] = ps.id
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "account_id": account_id,
                "picker_session_id": ps.id,
            }
        ),
        extra={"event": "picker.create.success"}
    )
    return jsonify(
        {
            "pickerSessionId": ps.id,
            "sessionId": ps.session_id,
            "pickerUri": ps.picker_uri,
            "expireTime": picker_data.get("expireTime"),
            "pollingConfig": picker_data.get("pollingConfig"),
            "pickingConfig": picker_data.get("pickingConfig"),
            "mediaItemsSet": picker_data.get("mediaItemsSet"),
        }
    )


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
    if count > 0:
        ps.media_items_set = True
    db.session.commit()
    return jsonify({"result": "ok", "count": count})


@bp.get("/picker/session/<path:session_id>")
@login_required
def api_picker_session_status(session_id):
    """Return status of a picker session."""
    ps = PickerSession.query.filter_by(session_id=session_id).first()
    if not ps:
        return jsonify({"error": "not_found"}), 404
    account = GoogleAccount.query.get(ps.account_id)
    selected = ps.selected_count
    if selected is None and account and account.status == "active" and ps.session_id:
        try:
            tokens = refresh_google_token(account)
            access_token = tokens.get("access_token")
            res = log_requests_and_send(
                "GET",
                f"https://photospicker.googleapis.com/v1/sessions/{ps.session_id}",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15,
            )
            res.raise_for_status()
            data = res.json()
            selected = (
                data.get("selectedCount")
                or data.get("selectedMediaCount")
                or data.get("selectedMediaItems")
            )
            _update_picker_session_from_data(ps, data)
        except Exception:
            selected = None
    ps.selected_count = selected
    ps.last_polled_at = datetime.now(timezone.utc)
    ps.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
                "status": ps.status,
            }
        ),
        extra={"event": "picker.status.get"}
    )
    return jsonify(
        {
            "status": ps.status,
            "selectedCount": ps.selected_count,
            "lastPolledAt": ps.last_polled_at.isoformat().replace("+00:00", "Z"),
            "serverTimeRFC1123": datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT'),
            "sessionId": ps.session_id,
            "pickerUri": ps.picker_uri,
            "expireTime": ps.expire_time.isoformat().replace("+00:00", "Z") if ps.expire_time else None,
            "pollingConfig": json.loads(ps.polling_config_json) if ps.polling_config_json else None,
            "pickingConfig": json.loads(ps.picking_config_json) if ps.picking_config_json else None,
            "mediaItemsSet": ps.media_items_set,
        }
    )


@bp.post("/picker/session/mediaItems")
@login_required
def api_picker_session_media_items():
    """Fetch selected media items from Google Photos Picker and store them."""

    data = request.get_json(silent=True) or {}
    session_id = data.get("sessionId")
    cursor = data.get("cursor")
    if not session_id or not isinstance(session_id, str):
        return jsonify({"error": "invalid_session"}), 400

    lock = _get_media_items_lock(session_id)
    if not lock.acquire(blocking=False):
        return jsonify({"error": "busy"}), 409

    try:
        ps = PickerSession.query.filter_by(session_id=session_id).first()
        if not ps or ps.status not in ("pending", "processing"):
            return jsonify({"error": "not_found"}), 404
        # ステータスをprocessingにし、updated_atも更新
        ps.status = "processing"
        ps.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        account = GoogleAccount.query.get(ps.account_id)
        if not account:
            return jsonify({"error": "not_found"}), 404
        try:
            tokens = refresh_google_token(account)
        except RefreshTokenError as e:
            status = 502 if e.status_code >= 500 else 401
            return jsonify({"error": str(e)}), status
        headers = {"Authorization": f"Bearer {tokens.get('access_token')}"}
        params = {"sessionId": session_id, "pageSize": 100}
        if cursor:
            params["pageToken"] = cursor
        saved = 0
        dup = 0
        while True:
            try:
                res = log_requests_and_send(
                    "GET",
                    "https://photospicker.googleapis.com/v1/mediaItems",
                    params=params,
                    headers=headers,
                    timeout=15,
                )
            except Exception as fetch_exc:
                res_text = getattr(fetch_exc, 'response', None)
                if res_text is not None:
                    res_text = res_text.text
                else:
                    res_text = None
                raise RuntimeError(f"mediaItems fetch failed: {fetch_exc}")

            if res.status_code == 429:
                time.sleep(1)
                continue
            try:
                res.raise_for_status()
                picker_data = res.json()
            except Exception as fetch_exc:
                res_text = getattr(fetch_exc, 'response', None)
                if res_text is not None:
                    res_text = res_text.text
                else:
                    res_text = None
                raise RuntimeError(f"mediaItems fetch failed: {fetch_exc}")

            items = picker_data.get("mediaItems") or []
            for item in items:
                item_id = item.get("id")
                if not item_id:
                    continue
                mi = MediaItem.query.get(item_id)
                if not mi:
                    mi = MediaItem(id=item_id, type="TYPE_UNSPECIFIED")

                pmi = PickedMediaItem.query.filter_by(
                    picker_session_id=ps.id, media_item_id=item_id
                ).first()
                is_dup = pmi is not None
                if not pmi:
                    pmi = PickedMediaItem(
                        picker_session_id=ps.id, media_item_id=item_id, status="pending"
                    )

                ct = item.get("createTime")
                if ct:
                    try:
                        pmi.create_time = datetime.fromisoformat(ct.replace("Z", "+00:00"))
                    except Exception:
                        pmi.create_time = None

                mf_dict = item.get("mediaFile")
                if isinstance(mf_dict, dict):
                    mi.mime_type = mf_dict.get("mimeType")
                    mi.filename = mf_dict.get("filename")
                    meta = mf_dict.get("mediaFileMetadata") or {}
                else:
                    meta = {}

                width = meta.get("width")
                height = meta.get("height")
                if width is not None:
                    try:
                        mi.width = int(width)
                    except Exception:
                        mi.width = None
                if height is not None:
                    try:
                        mi.height = int(height)
                    except Exception:
                        mi.height = None
                mi.camera_make = meta.get("cameraMake")
                mi.camera_model = meta.get("cameraModel")

                photo_meta = meta.get("photoMetadata") or {}
                video_meta = meta.get("videoMetadata") or {}

                if photo_meta:
                    if mi.photo_metadata:
                        pm = mi.photo_metadata
                    else:
                        pm = PhotoMetadata()
                    pm.focal_length = photo_meta.get("focalLength")
                    pm.aperture_f_number = photo_meta.get("apertureFNumber")
                    pm.iso_equivalent = photo_meta.get("isoEquivalent")
                    pm.exposure_time = photo_meta.get("exposureTime")
                    mi.photo_metadata = pm
                    mi.type = "PHOTO"

                if video_meta:
                    if mi.video_metadata:
                        vm = mi.video_metadata
                    else:
                        vm = VideoMetadata()
                    vm.fps = video_meta.get("fps")
                    vm.processing_status = video_meta.get("processingStatus")
                    mi.video_metadata = vm
                    mi.type = "VIDEO"

                pmi.updated_at = datetime.now(timezone.utc)
                db.session.add(mi)
                db.session.add(pmi)
                if is_dup:
                    dup += 1
                else:
                    saved += 1

            cursor = picker_data.get("nextPageToken")
            if cursor:
                params["pageToken"] = cursor
                continue
            break

        # ステータスをimportedにし、updated_atも更新
        ps.status = "imported"
        ps.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        return jsonify({"saved": saved, "duplicates": dup, "nextCursor": None})
    except Exception as e:
        db.session.rollback()
        ps.status = "pending"
        ps.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        res_text = None
        if hasattr(e, '__cause__') and hasattr(e.__cause__, 'response'):
            res_obj = getattr(e.__cause__, 'response', None)
            if res_obj is not None:
                res_text = res_obj.text
        current_app.logger.error(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "session_id": session_id,
                    "error": str(e),
                    "detail": res_text,
                }
            ),
            extra={"event": "picker.mediaItems.fail"}
        )
        return jsonify({"error": "picker_error", "message": str(e)}), 502
    finally:
        lock.release()
        _release_media_items_lock(session_id, lock)


@bp.post("/picker/session/<path:picker_session_id>/import")
@login_required
def api_picker_session_import(picker_session_id):
    """Enqueue import task for picker session.

    The frontend does not pass ``account_id`` in the request body, so the
    parameter is now optional.  If provided it must match the session's
    ``account_id``; otherwise the session's own ``account_id`` is used.
    The picker session status is also updated to ``importing`` so that the
    client can immediately reflect the change in state.
    """
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    ps = PickerSession.query.filter_by(session_id=picker_session_id).first()
    if not ps or (account_id and ps.account_id != account_id):
        return jsonify({"error": "not_found"}), 404
    # Use the session's account id when not explicitly supplied
    account_id = account_id or ps.account_id
    if ps.status in ("imported", "canceled", "expired"):
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "picker_session_id": picker_session_id,
                    "status": ps.status,
                }
            ),
            extra={"event": "picker.import.suppress"}
        )
        return jsonify({"error": "already_done"}), 409
    stats = ps.stats()
    if stats.get("celery_task_id"):
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "picker_session_id": picker_session_id,
                    "status": ps.status,
                }
            ),
            extra={"event": "picker.import.suppress"}
        )
        return jsonify({"error": "already_enqueued"}), 409
    task_id = uuid4().hex
    stats["celery_task_id"] = task_id
    ps.set_stats(stats)
    ps.status = "importing"
    db.session.commit()
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "picker_session_id": picker_session_id,
                "status": ps.status,
            }
        ),
        extra={"event": "picker.import.enqueue"}
    )
    return jsonify({"enqueued": True, "celeryTaskId": task_id}), 202
