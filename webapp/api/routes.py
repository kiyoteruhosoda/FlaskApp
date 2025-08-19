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
