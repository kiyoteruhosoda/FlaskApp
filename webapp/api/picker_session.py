from datetime import datetime, timezone
import json
from uuid import uuid4
from flask import (
        Blueprint, current_app, jsonify, request, session
)
from flask_login import login_required
from ..extensions import db
from core.models.google_account import GoogleAccount
from core.models.picker_session import PickerSession
from core.models.picker_import_item import PickerImportItem
from core.models.photo_models import (
    PickedMediaItem,
    MediaFileMetadata,
    PhotoMetadata,
    VideoMetadata,
)
from core.crypto import decrypt
from ..auth.utils import refresh_google_token, RefreshTokenError, log_requests_and_send

bp = Blueprint('picker_session_api', __name__)

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
        db.session.commit()
        ps.session_id = picker_data.get("sessionId") or picker_data.get("name")
        ps.picker_uri = picker_data.get("pickerUri")
        expire = picker_data.get("expireTime")
        if expire:
                try:
                        ps.expire_time = datetime.fromisoformat(expire.replace("Z", "+00:00"))
                except Exception:
                        ps.expire_time = None
        if picker_data.get("pollingConfig"):
                ps.polling_config_json = json.dumps(picker_data.get("pollingConfig"))
        if picker_data.get("pickingConfig"):
                ps.picking_config_json = json.dumps(picker_data.get("pickingConfig"))
        if "mediaItemsSet" in picker_data:
                ps.media_items_set = picker_data.get("mediaItemsSet")
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
                        "expireTime": expire,
                        "pollingConfig": picker_data.get("pollingConfig"),
                        "pickingConfig": picker_data.get("pickingConfig"),
                        "mediaItemsSet": picker_data.get("mediaItemsSet"),
                }
        )


@bp.post("/picker/session/<int:picker_session_id>/callback")
def api_picker_session_callback(picker_session_id):
        """Receive selected media item IDs from Google Photos Picker."""
        ps = PickerSession.query.get(picker_session_id)
        if not ps:
                return jsonify({"error": "not_found"}), 404
        data = request.get_json(silent=True) or {}
        ids = data.get("mediaItemIds") or []
        if isinstance(ids, str):
                ids = [ids]
        saved = 0
        for mid in ids:
                if not isinstance(mid, str):
                        continue
                exists = PickerImportItem.query.filter_by(
                        picker_session_id=ps.id, media_item_id=mid
                ).first()
                if exists:
                        continue
                db.session.add(PickerImportItem(picker_session_id=ps.id, media_item_id=mid))
                saved += 1
        ps.selected_count = (ps.selected_count or 0) + saved
        ps.status = "ready"
        if saved > 0:
                ps.media_items_set = True
        db.session.commit()
        return jsonify({"result": "ok", "count": saved})


@bp.get("/picker/session/<int:picker_session_id>")
@login_required
def api_picker_session_status(picker_session_id):
        """Return status of a picker session."""
        ps = PickerSession.query.get(picker_session_id)
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
                                f"https://photospicker.googleapis.com/v1/{ps.session_id}",
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
                        if data.get("expireTime"):
                                try:
                                        ps.expire_time = datetime.fromisoformat(
                                                data["expireTime"].replace("Z", "+00:00")
                                        )
                                except Exception:
                                        pass
                        if data.get("pollingConfig"):
                                ps.polling_config_json = json.dumps(data.get("pollingConfig"))
                        if data.get("pickingConfig"):
                                ps.picking_config_json = json.dumps(data.get("pickingConfig"))
                        if "mediaItemsSet" in data:
                                ps.media_items_set = data.get("mediaItemsSet")
                except Exception:
                        selected = None
        ps.selected_count = selected
        ps.last_polled_at = datetime.now(timezone.utc)
        db.session.commit()
        current_app.logger.info(
                json.dumps(
                        {
                                "ts": datetime.now(timezone.utc).isoformat(),
                                "picker_session_id": picker_session_id,
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
    ps = PickerSession.query.filter_by(session_id=session_id).first()
    if not ps:
        return jsonify({"error": "not_found"}), 404
    account = GoogleAccount.query.get(ps.account_id)
    if not account:
        return jsonify({"error": "not_found"}), 404
    try:
        tokens = refresh_google_token(account)
    except RefreshTokenError as e:
        status = 502 if e.status_code >= 500 else 401
        return jsonify({"error": str(e)}), status
    headers = {"Authorization": f"Bearer {tokens.get('access_token')}"}
    body = {"sessionId": session_id}
    if cursor:
        body["pageToken"] = cursor
    try:
        res = log_requests_and_send(
            "POST",
            "https://photospicker.googleapis.com/v1/mediaItems",
            json_data=body,
            headers=headers,
            timeout=15,
        )
        res.raise_for_status()
        picker_data = res.json()
    except Exception as e:
        return jsonify({"error": "picker_error", "message": str(e)}), 502
    items = picker_data.get("mediaItems") or []
    saved = 0
    dup = 0
    for item in items:
        item_id = item.get("id") or item.get("mediaItemId")
        if not item_id:
            continue
        pmi = PickedMediaItem.query.get(item_id)
        is_dup = pmi is not None
        if not pmi:
            pmi = PickedMediaItem(id=item_id, status="pending")
        pmi.base_url = item.get("baseUrl")
        pmi.mime_type = item.get("mimeType")
        pmi.filename = item.get("filename")
        meta = item.get("mediaMetadata") or {}
        ctime = meta.get("creationTime")
        if ctime:
            try:
                pmi.create_time = datetime.fromisoformat(ctime.replace("Z", "+00:00"))
            except Exception:
                pass
        pmi.type = "VIDEO" if meta.get("video") else "PHOTO"
        mf = pmi.media_file_metadata or MediaFileMetadata()
        width = meta.get("width")
        height = meta.get("height")
        if width is not None:
            try:
                mf.width = int(width)
            except Exception:
                mf.width = None
        if height is not None:
            try:
                mf.height = int(height)
            except Exception:
                mf.height = None
        photo_meta = meta.get("photo") or {}
        if photo_meta:
            mf.camera_make = photo_meta.get("cameraMake")
            mf.camera_model = photo_meta.get("cameraModel")
            pm = mf.photo_metadata or PhotoMetadata()
            pm.focal_length = photo_meta.get("focalLength")
            pm.aperture_f_number = photo_meta.get("apertureFNumber")
            pm.iso_equivalent = photo_meta.get("isoEquivalent")
            pm.exposure_time = photo_meta.get("exposureTime")
            mf.photo_metadata = pm
        video_meta = meta.get("video") or {}
        if video_meta:
            mf.camera_make = video_meta.get("cameraMake") or mf.camera_make
            mf.camera_model = video_meta.get("cameraModel") or mf.camera_model
            vm = mf.video_metadata or VideoMetadata()
            vm.fps = video_meta.get("fps")
            vm.processing_status = video_meta.get("status")
            mf.video_metadata = vm
        pmi.media_file_metadata = mf
        db.session.add(pmi)
        if is_dup:
            dup += 1
        else:
            saved += 1
    db.session.commit()
    return jsonify(
        {"saved": saved, "duplicates": dup, "nextCursor": picker_data.get("nextPageToken")}
    )


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
