from datetime import datetime, timezone
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import time
from urllib.parse import urlencode
from email.utils import formatdate
from uuid import uuid4

import requests
from flask import (
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    flash,
)
from flask_login import login_required
from flask_babel import gettext as _

from . import bp
from ..extensions import db
from core.models.google_account import GoogleAccount
from core.models.picker_session import PickerSession
from core.models.picker_import_item import PickerImportItem
from core.models.photo_models import Media, Exif, MediaSidecar, MediaPlayback
from core.crypto import decrypt, encrypt




@bp.post("/google/oauth/start")
@login_required
def google_oauth_start():
    """Start Google OAuth flow by returning an authorization URL."""
    data = request.get_json(silent=True) or {}
    scopes = data.get("scopes") or []
    redirect_target = data.get("redirect")
    state = secrets.token_urlsafe(16)
    session["google_oauth_state"] = {
        "state": state,
        "scopes": scopes,
        "redirect": redirect_target,
    }
    params = {
        "client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
        "redirect_uri": url_for("auth.google_oauth_callback", _external=True),
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return jsonify({"auth_url": auth_url, "server_time": datetime.now(timezone.utc).isoformat()})



@bp.get("/google/accounts")
@login_required
def api_google_accounts():
    """Return list of linked Google accounts."""
    accounts = GoogleAccount.query.all()
    return jsonify(
        [
            {
                "id": a.id,
                "email": a.email,
                "status": a.status,
                "scopes": a.scopes_list(),
                "last_synced_at": a.last_synced_at.isoformat() if a.last_synced_at else None,
                "has_token": bool(a.oauth_token_json),
            }
            for a in accounts
        ]
    )


@bp.patch("/google/accounts/<int:account_id>")
@login_required
def api_google_account_update(account_id):
    """Update status of a Google account."""
    account = GoogleAccount.query.get_or_404(account_id)
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in ("active", "disabled"):
        return jsonify({"error": "invalid_status"}), 400
    account.status = status
    db.session.commit()
    return jsonify({"result": "ok", "status": account.status})


@bp.delete("/google/accounts/<int:account_id>")
@login_required
def api_google_account_delete(account_id):
    """Delete a linked Google account and revoke token."""
    account = GoogleAccount.query.get_or_404(account_id)
    token_json = json.loads(decrypt(account.oauth_token_json) or "{}")
    refresh_token = token_json.get("refresh_token")
    if refresh_token:
        try:
            requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": refresh_token},
                timeout=10,
            )
        except Exception:
            pass
    db.session.delete(account)
    db.session.commit()
    return jsonify({"result": "deleted"})


@bp.post("/google/accounts/<int:account_id>/test")
@login_required
def api_google_account_test(account_id):
    """Test refresh token by attempting to obtain a new access token."""
    account = GoogleAccount.query.get_or_404(account_id)
    tokens = json.loads(decrypt(account.oauth_token_json) or "{}")
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "no_refresh_token"}), 400
    data = {
        "client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
        "client_secret": current_app.config.get("GOOGLE_CLIENT_SECRET"),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    try:
        res = requests.post("https://oauth2.googleapis.com/token", data=data, timeout=10)
        result = res.json()
        if "error" in result:
            return jsonify({"error": result["error"]}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    tokens.update(result)
    account.oauth_token_json = encrypt(json.dumps(tokens))
    account.last_synced_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"result": "ok"})


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

    tokens = json.loads(decrypt(account.oauth_token_json) or "{}")
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "no_refresh_token"}), 401
    token_req = {
        "client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
        "client_secret": current_app.config.get("GOOGLE_CLIENT_SECRET"),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    try:
        token_res = requests.post(
            "https://oauth2.googleapis.com/token", data=token_req, timeout=15
        )
        token_data = token_res.json()
        if "access_token" not in token_data:
            current_app.logger.error(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "account_id": account_id,
                        "response": token_data,
                    }
                ),
                extra={"event": "picker.create.fail"}
            )
            return (
                jsonify(
                    {
                        "error": token_data.get("error", "oauth_error"),
                        "message": token_data.get("error_description"),
                    }
                ),
                401,
            )
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
        return jsonify({"error": "oauth_error", "message": str(e)}), 502

    access_token = token_data["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    body = {"title": title}
    try:
        picker_res = requests.post(
            "https://photospicker.googleapis.com/v1/sessions",
            json=body,
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
            tokens = json.loads(decrypt(account.oauth_token_json) or "{}")
            refresh_token = tokens.get("refresh_token")
            if refresh_token:
                token_req = {
                    "client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
                    "client_secret": current_app.config.get("GOOGLE_CLIENT_SECRET"),
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                }
                token_res = requests.post(
                    "https://oauth2.googleapis.com/token", data=token_req, timeout=15
                )
                token_data = token_res.json()
                access_token = token_data.get("access_token")
                if access_token:
                    res = requests.get(
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
            "serverTimeRFC1123": formatdate(usegmt=True),
            "sessionId": ps.session_id,
            "pickerUri": ps.picker_uri,
            "expireTime": ps.expire_time.isoformat().replace("+00:00", "Z") if ps.expire_time else None,
            "pollingConfig": json.loads(ps.polling_config_json) if ps.polling_config_json else None,
            "pickingConfig": json.loads(ps.picking_config_json) if ps.picking_config_json else None,
            "mediaItemsSet": ps.media_items_set,
        }
    )


@bp.post("/picker/session/<int:picker_session_id>/import")
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
    ps = PickerSession.query.get(picker_session_id)
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


@bp.get("/media")
@login_required
def api_media_list():
    """Return paginated list of media items."""
    trace = uuid4().hex
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "trace": trace,
                "cursor": request.args.get("cursor"),
                "limit": request.args.get("limit"),
            }
        ),
        extra={"event": "media.list.begin"}
    )
    try:
        limit = int(request.args.get("limit", 200))
    except Exception:
        limit = 200
    limit = max(1, min(limit, 200))
    cursor = request.args.get("cursor", type=int)
    include_deleted = request.args.get("include_deleted", type=int, default=0)
    after_param = request.args.get("after")
    before_param = request.args.get("before")

    query = Media.query
    if not include_deleted:
        query = query.filter(Media.is_deleted.is_(False))
    if cursor is not None:
        query = query.filter(Media.id <= cursor)
    if after_param:
        try:
            after_dt = datetime.fromisoformat(after_param.replace("Z", "+00:00"))
            query = query.filter(Media.shot_at >= after_dt)
        except Exception:
            pass
    if before_param:
        try:
            before_dt = datetime.fromisoformat(before_param.replace("Z", "+00:00"))
            query = query.filter(Media.shot_at <= before_dt)
        except Exception:
            pass

    query = query.order_by(
        Media.shot_at.is_(None),
        Media.shot_at.desc(),
        Media.imported_at.desc(),
        Media.id.desc(),
    )
    items = query.limit(limit).all()

    next_cursor = None
    if len(items) == limit:
        last_id = items[-1].id
        if last_id and last_id > 1:
            next_cursor = last_id - 1

    data_items = []
    for m in items:
        data_items.append(
            {
                "id": m.id,
                "shot_at": m.shot_at.isoformat().replace("+00:00", "Z")
                if m.shot_at
                else None,
                "mime_type": m.mime_type,
                "width": m.width,
                "height": m.height,
                "is_video": int(bool(m.is_video)),
                "local_rel_path": m.local_rel_path,
                "has_playback": int(bool(m.has_playback)),
            }
        )

    server_time = formatdate(usegmt=True)
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "trace": trace,
                "count": len(items),
                "cursor": cursor,
                "nextCursor": next_cursor,
                "serverTimeRFC1123": server_time,
            }
        ),
        extra={"event": "media.list.success"}
    )
    return jsonify(
        {"items": data_items, "nextCursor": next_cursor, "serverTimeRFC1123": server_time}
    )


@bp.get("/media/<int:media_id>")
@login_required
def api_media_detail(media_id):
    """Return detailed info for a single media item."""
    trace = uuid4().hex
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "media_id": media_id,
                "trace": trace,
            }
        ),
        extra={"event": "media.detail.begin"}
    )
    media = Media.query.get(media_id)
    if not media or media.is_deleted:
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "media_id": media_id,
                    "trace": trace,
                }
            ),
            extra={"event": "media.detail.not_found"}
        )
        return jsonify({"error": "not_found"}), 404

    exif = media.exif
    sidecars = [
        {"type": s.type, "rel_path": s.rel_path, "bytes": s.bytes}
        for s in media.sidecars
    ]
    pb = media.playbacks[0] if media.playbacks else None
    playback = {
        "available": bool(pb and pb.status == "done"),
        "preset": pb.preset if pb else None,
        "rel_path": pb.rel_path if pb else None,
        "status": pb.status if pb else None,
    }

    data = {
        "id": media.id,
        "google_media_id": media.google_media_id,
        "account_id": media.account_id,
        "local_rel_path": media.local_rel_path,
        "bytes": media.bytes,
        "mime_type": media.mime_type,
        "width": media.width,
        "height": media.height,
        "duration_ms": media.duration_ms,
        "shot_at": media.shot_at.isoformat().replace("+00:00", "Z")
        if media.shot_at
        else None,
        "imported_at": media.imported_at.isoformat().replace("+00:00", "Z")
        if media.imported_at
        else None,
        "is_video": int(bool(media.is_video)),
        "is_deleted": int(bool(media.is_deleted)),
        "has_playback": int(bool(media.has_playback)),
        "exif": {
            "camera_make": exif.camera_make if exif else None,
            "camera_model": exif.camera_model if exif else None,
            "lens": exif.lens if exif else None,
            "iso": exif.iso if exif else None,
            "shutter": exif.shutter if exif else None,
            "f_number": float(exif.f_number)
            if exif and exif.f_number is not None
            else None,
            "focal_len": float(exif.focal_len)
            if exif and exif.focal_len is not None
            else None,
            "gps_lat": float(exif.gps_lat)
            if exif and exif.gps_lat is not None
            else None,
            "gps_lng": float(exif.gps_lng)
            if exif and exif.gps_lng is not None
            else None,
        },
        "sidecars": sidecars,
        "playback": playback,
    }

    server_time = formatdate(usegmt=True)
    data["serverTimeRFC1123"] = server_time
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "media_id": media_id,
                "trace": trace,
                "serverTimeRFC1123": server_time,
            }
        ),
        extra={"event": "media.detail.success"}
    )
    return jsonify(data)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign_payload(payload: dict) -> str:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    key_b64 = current_app.config.get("FPV_DL_SIGN_KEY")
    key = _b64url_decode(key_b64) if key_b64 else b""
    sig = hmac.new(key, canonical, hashlib.sha256).digest()
    return f"{_b64url_encode(canonical)}.{_b64url_encode(sig)}"


def _verify_token(token: str):
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes)
    except Exception:
        return None, "invalid_token"

    key_b64 = current_app.config.get("FPV_DL_SIGN_KEY")
    key = _b64url_decode(key_b64) if key_b64 else b""
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    expected_sig = hmac.new(key, canonical, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_sig, _b64url_decode(sig_b64)):
        return None, "invalid_token"

    if payload.get("exp", 0) < int(time.time()):
        return None, "expired"

    return payload, None


@bp.post("/media/<int:media_id>/thumb-url")
@login_required
def api_media_thumb_url(media_id):
    data = request.get_json(silent=True) or {}
    size = data.get("size")
    if size not in (256, 1024, 2048):
        return jsonify({"error": "invalid_size"}), 400

    media = Media.query.get(media_id)
    if not media:
        return jsonify({"error": "not_found"}), 404
    if media.is_deleted:
        return jsonify({"error": "gone"}), 410

    rel_path = media.local_rel_path
    token_path = f"thumbs/{size}/{rel_path}"
    abs_path = os.path.join(current_app.config.get("FPV_NAS_THUMBS_DIR", ""), str(size), rel_path)
    if not os.path.exists(abs_path):
        return jsonify({"error": "not_found"}), 404

    ct = mimetypes.guess_type(abs_path)[0] or media.mime_type or "application/octet-stream"
    ttl = current_app.config.get("FPV_URL_TTL_THUMB", 600)
    exp = int(time.time()) + ttl
    payload = {
        "v": 1,
        "typ": "thumb",
        "mid": media_id,
        "size": size,
        "path": token_path,
        "ct": ct,
        "exp": exp,
        "nonce": uuid4().hex,
    }
    token = _sign_payload(payload)
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "mid": media_id,
                "size": size,
                "ttl": ttl,
                "nonce": payload["nonce"],
            }
        ),
        extra={"event": "url.thumb.issue"}
    )
    return (
        jsonify(
            {
                "url": f"/api/dl/{token}",
                "expiresAt": expires_at,
                "cacheControl": f"private, max-age={ttl}",
            }
        ),
        200,
    )


@bp.post("/media/<int:media_id>/playback-url")
@login_required
def api_media_playback_url(media_id):
    media = Media.query.get(media_id)
    if not media or not media.is_video:
        return jsonify({"error": "not_found"}), 404
    if media.is_deleted:
        return jsonify({"error": "gone"}), 410

    pb = MediaPlayback.query.filter_by(media_id=media_id, preset="std1080p").first()
    if not pb or pb.status == "error":
        return jsonify({"error": "not_found"}), 404
    if pb.status in ("pending", "processing"):
        return jsonify({"error": "not_ready"}), 409
    if pb.status != "done":
        return jsonify({"error": "not_found"}), 404

    token_path = f"playback/{pb.rel_path}"
    abs_path = os.path.join(current_app.config.get("FPV_NAS_PLAY_DIR", ""), pb.rel_path)
    if not os.path.exists(abs_path):
        return jsonify({"error": "not_found"}), 404
    ct = mimetypes.guess_type(abs_path)[0] or "video/mp4"
    ttl = current_app.config.get("FPV_URL_TTL_PLAYBACK", 600)
    exp = int(time.time()) + ttl
    payload = {
        "v": 1,
        "typ": "playback",
        "mid": media_id,
        "size": None,
        "path": token_path,
        "ct": ct,
        "exp": exp,
        "nonce": uuid4().hex,
    }
    token = _sign_payload(payload)
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "mid": media_id,
                "ttl": ttl,
                "nonce": payload["nonce"],
            }
        ),
        extra={"event": "url.playback.issue"}
    )
    return (
        jsonify(
            {
                "url": f"/api/dl/{token}",
                "expiresAt": expires_at,
                "cacheControl": f"private, max-age={ttl}",
            }
        ),
        200,
    )


@bp.route("/dl/<path:token>", methods=["GET", "HEAD"])
def api_download(token):
    payload, err = _verify_token(token)
    if err:
        return jsonify({"error": err}), 403

    path = payload.get("path", "")
    ct = payload.get("ct", "application/octet-stream")
    if ".." in path.split("/"):
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "mid": payload.get("mid"),
                    "nonce": payload.get("nonce"),
                }
            ),
            extra={"event": "dl.forbidden"}
        )
        return jsonify({"error": "forbidden"}), 403

    if payload.get("typ") == "thumb":
        if not path.startswith("thumbs/"):
            return jsonify({"error": "forbidden"}), 403
        rel = path[len("thumbs/") :]
        base = current_app.config.get("FPV_NAS_THUMBS_DIR", "")
    else:
        if not path.startswith("playback/"):
            return jsonify({"error": "forbidden"}), 403
        rel = path[len("playback/") :]
        base = current_app.config.get("FPV_NAS_PLAY_DIR", "")
    abs_path = os.path.join(base, rel)
    if not os.path.exists(abs_path):
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "mid": payload.get("mid"),
                    "nonce": payload.get("nonce"),
                }
            ),
            extra={"event": "dl.notfound"}
        )
        return jsonify({"error": "not_found"}), 404

    guessed = mimetypes.guess_type(abs_path)[0]
    if guessed != ct:
        return jsonify({"error": "forbidden"}), 403

    size = os.path.getsize(abs_path)
    cache_control = f"private, max-age={current_app.config.get('FPV_URL_TTL_THUMB' if payload.get('typ') == 'thumb' else 'FPV_URL_TTL_PLAYBACK', 600)}"
    range_header = request.headers.get("Range")
    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if m:
            start = int(m.group(1))
            end = int(m.group(2) or size - 1)
            end = min(end, size - 1)
            length = end - start + 1
            with open(abs_path, "rb") as f:
                f.seek(start)
                data = f.read(length)
            resp = current_app.response_class(data, 206, mimetype=ct, direct_passthrough=True)
            resp.headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            resp.headers["Accept-Ranges"] = "bytes"
            resp.headers["Content-Length"] = str(length)
            resp.headers["Cache-Control"] = cache_control
            current_app.logger.info(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "mid": payload.get("mid"),
                        "nonce": payload.get("nonce"),
                        "start": start,
                        "end": end,
                    }
                ), extra={"event": "dl.range"}
            )
            return resp

    if request.method == "HEAD":
        resp = current_app.response_class(b"", mimetype=ct)
        resp.headers["Content-Length"] = str(size)
        resp.headers["Accept-Ranges"] = "bytes"
        resp.headers["Cache-Control"] = cache_control
        return resp

    with open(abs_path, "rb") as f:
        data = f.read()
    resp = current_app.response_class(data, mimetype=ct, direct_passthrough=True)
    resp.headers["Content-Length"] = str(size)
    resp.headers["Accept-Ranges"] = "bytes"
    resp.headers["Cache-Control"] = cache_control
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "mid": payload.get("mid"),
                "nonce": payload.get("nonce"),
            }
        ),
        extra={"event": "dl.success"}
    )
    return resp
