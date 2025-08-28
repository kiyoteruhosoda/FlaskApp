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
from core.models.photo_models import Media, Exif, MediaSidecar, MediaPlayback
from core.crypto import decrypt
from ..auth.utils import refresh_google_token, RefreshTokenError, log_requests_and_send
from .pagination import PaginationParams, paginate_and_respond


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
    return jsonify(
        {"auth_url": auth_url, "server_time": datetime.now(timezone.utc).isoformat()}
    )


@bp.get("/google/accounts")
@login_required
def api_google_accounts():
    """Return paginated list of linked Google accounts."""
    
    # ページングパラメータの取得
    params = PaginationParams.from_request(default_page_size=200)
    
    # ベースクエリ
    query = GoogleAccount.query
    
    # Googleアカウントのシリアライザ関数
    def serialize_google_account(account):
        return {
            "id": account.id,
            "email": account.email,
            "status": account.status,
            "scopes": account.scopes_list(),
            "last_synced_at": (
                account.last_synced_at.isoformat() if account.last_synced_at else None
            ),
            "has_token": bool(account.oauth_token_json),
        }
    
    # ページング処理
    result = paginate_and_respond(
        query=query,
        params=params,
        serializer_func=serialize_google_account,
        id_column=GoogleAccount.id,
        count_total=not params.use_cursor,
        default_page_size=200
    )
    
    return jsonify(result)


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
            log_requests_and_send(
                "POST",
                "https://oauth2.googleapis.com/revoke",
                data={"token": refresh_token},
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
    try:
        refresh_google_token(account)
    except RefreshTokenError as e:
        return jsonify({"error": str(e)}), e.status_code
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
        extra={"event": "media.list.begin"},
    )
    
    # ページングパラメータの取得
    params = PaginationParams.from_request(default_page_size=200)
    
    # フィルタパラメータ
    include_deleted = request.args.get("include_deleted", type=int, default=0)
    after_param = request.args.get("after")
    before_param = request.args.get("before")
    
    # ベースクエリの構築
    query = Media.query
    if not include_deleted:
        query = query.filter(Media.is_deleted.is_(False))
        
    # 日付範囲フィルタ
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
    
    # メディアアイテムのシリアライザ関数
    def serialize_media_item(media):
        return {
            "id": media.id,
            "shot_at": (
                media.shot_at.isoformat().replace("+00:00", "Z") if media.shot_at else None
            ),
            "mime_type": media.mime_type,
            "width": media.width,
            "height": media.height,
            "is_video": int(bool(media.is_video)),
            "local_rel_path": media.local_rel_path,
            "has_playback": int(bool(media.has_playback)),
        }
    
    # ページング処理
    result = paginate_and_respond(
        query=query,
        params=params,
        serializer_func=serialize_media_item,
        id_column=Media.id,
        shot_at_column=Media.shot_at,
        count_total=False,  # 高速化のため総件数はカウントしない
        default_page_size=200
    )
    
    # ログ出力
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "trace": trace,
                "count": len(result["items"]),
                "cursor": params.cursor,
                "nextCursor": result.get("nextCursor"),
                "serverTimeRFC1123": result.get("serverTimeRFC1123"),
            }
        ),
        extra={"event": "media.list.success"},
    )
    
    return jsonify(result)


def build_playback_dict(playback: MediaPlayback | None) -> dict:
    """Return playback information dictionary."""
    return {
        "available": bool(playback and playback.status == "done"),
        "preset": playback.preset if playback else None,
        "rel_path": playback.rel_path if playback else None,
        "status": playback.status if playback else None,
    }


def build_exif_dict(exif: Exif | None) -> dict:
    """Return EXIF information dictionary."""
    return {
        "camera_make": exif.camera_make if exif else None,
        "camera_model": exif.camera_model if exif else None,
        "lens": exif.lens if exif else None,
        "iso": exif.iso if exif else None,
        "shutter": exif.shutter if exif else None,
        "f_number": (
            float(exif.f_number) if exif and exif.f_number is not None else None
        ),
        "focal_len": (
            float(exif.focal_len) if exif and exif.focal_len is not None else None
        ),
        "gps_lat": float(exif.gps_lat) if exif and exif.gps_lat is not None else None,
        "gps_lng": float(exif.gps_lng) if exif and exif.gps_lng is not None else None,
    }


def serialize_media_detail(media: Media) -> dict:
    """Serialize detailed information for a media item."""
    sidecars = [
        {"type": s.type, "rel_path": s.rel_path, "bytes": s.bytes}
        for s in media.sidecars
    ]
    playback_record = media.playbacks[0] if media.playbacks else None
    return {
        "id": media.id,
        "google_media_id": media.google_media_id,
        "account_id": media.account_id,
        "local_rel_path": media.local_rel_path,
        "bytes": media.bytes,
        "mime_type": media.mime_type,
        "width": media.width,
        "height": media.height,
        "duration_ms": media.duration_ms,
        "shot_at": (
            media.shot_at.isoformat().replace("+00:00", "Z") if media.shot_at else None
        ),
        "imported_at": (
            media.imported_at.isoformat().replace("+00:00", "Z")
            if media.imported_at
            else None
        ),
        "is_video": int(bool(media.is_video)),
        "is_deleted": int(bool(media.is_deleted)),
        "has_playback": int(bool(media.has_playback)),
        "exif": build_exif_dict(media.exif),
        "sidecars": sidecars,
        "playback": build_playback_dict(playback_record),
    }


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
        extra={"event": "media.detail.begin"},
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
            extra={"event": "media.detail.not_found"},
        )
        return jsonify({"error": "not_found"}), 404

    media_data = serialize_media_detail(media)

    server_time = formatdate(usegmt=True)
    media_data["serverTimeRFC1123"] = server_time
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "media_id": media_id,
                "trace": trace,
                "serverTimeRFC1123": server_time,
            }
        ),
        extra={"event": "media.detail.success"},
    )
    return jsonify(media_data)


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
        if _b64url_encode(payload_bytes) != payload_b64:
            return None, "invalid_token"
        payload = json.loads(payload_bytes)
    except Exception:
        return None, "invalid_token"

    key_b64 = current_app.config.get("FPV_DL_SIGN_KEY")
    key = _b64url_decode(key_b64) if key_b64 else b""
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    expected_sig = hmac.new(key, canonical, hashlib.sha256).digest()
    sig_bytes = _b64url_decode(sig_b64)
    if _b64url_encode(sig_bytes) != sig_b64:
        return None, "invalid_token"
    if not hmac.compare_digest(expected_sig, sig_bytes):
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
    abs_path = os.path.join(
        current_app.config.get("FPV_NAS_THUMBS_DIR", ""), str(size), rel_path
    )
    if not os.path.exists(abs_path):
        return jsonify({"error": "not_found"}), 404

    ct = (
        mimetypes.guess_type(abs_path)[0]
        or media.mime_type
        or "application/octet-stream"
    )
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
    expires_at = (
        datetime.fromtimestamp(exp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    )
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
        extra={"event": "url.thumb.issue"},
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
    expires_at = (
        datetime.fromtimestamp(exp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    )
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "mid": media_id,
                "ttl": ttl,
                "nonce": payload["nonce"],
            }
        ),
        extra={"event": "url.playback.issue"},
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
            extra={"event": "dl.forbidden"},
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
            extra={"event": "dl.notfound"},
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
            resp = current_app.response_class(
                data, 206, mimetype=ct, direct_passthrough=True
            )
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
                ),
                extra={"event": "dl.range"},
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
        extra={"event": "dl.success"},
    )
    return resp


@bp.post("/sync/local-import")
@login_required
def trigger_local_import():
    """ローカルファイル取り込みを手動実行"""
    from cli.src.celery.tasks import local_import_task_celery
    
    try:
        # Celeryタスクを非同期実行
        task = local_import_task_celery.delay()
        
        return jsonify({
            "success": True,
            "task_id": task.id,
            "message": "ローカルインポートタスクを開始しました",
            "server_time": datetime.now(timezone.utc).isoformat()
        })
    
    except Exception as e:
        current_app.logger.error(f"Failed to start local import task: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "server_time": datetime.now(timezone.utc).isoformat()
        }), 500


@bp.get("/sync/local-import/status")
@login_required
def local_import_status():
    """ローカルインポートの設定と状態を取得"""
    from webapp.config import Config
    
    # 設定情報
    import_dir = Config.LOCAL_IMPORT_DIR
    originals_dir = Config.FPV_NAS_ORIGINALS_DIR
    
    # ディレクトリの存在確認
    import_dir_exists = os.path.exists(import_dir) if import_dir else False
    originals_dir_exists = os.path.exists(originals_dir) if originals_dir else False
    
    # 取り込み対象ファイル数の計算
    file_count = 0
    if import_dir_exists:
        try:
            from core.tasks.local_import import scan_import_directory
            files = scan_import_directory(import_dir)
            file_count = len(files)
        except Exception as e:
            current_app.logger.warning(f"Failed to scan import directory: {e}")
    
    return jsonify({
        "config": {
            "import_dir": import_dir,
            "originals_dir": originals_dir,
            "import_dir_exists": import_dir_exists,
            "originals_dir_exists": originals_dir_exists
        },
        "status": {
            "pending_files": file_count,
            "ready": import_dir_exists and originals_dir_exists
        },
        "server_time": datetime.now(timezone.utc).isoformat()
    })


@bp.get("/sync/local-import/task/<task_id>")
@login_required
def get_local_import_task_result(task_id):
    """ローカルインポートタスクの結果を取得"""
    from cli.src.celery.celery_app import celery
    
    try:
        # タスクの結果を取得
        result = celery.AsyncResult(task_id)
        
        if result.state == 'PENDING':
            response = {
                "state": result.state,
                "status": "タスクが実行待ちです",
                "progress": 0
            }
        elif result.state == 'PROGRESS':
            response = {
                "state": result.state,
                "status": result.info.get('status', ''),
                "progress": result.info.get('progress', 0),
                "current": result.info.get('current', 0),
                "total": result.info.get('total', 0),
                "message": result.info.get('message', '')
            }
        elif result.state == 'SUCCESS':
            response = {
                "state": result.state,
                "status": "完了",
                "progress": 100,
                "result": result.result
            }
        else:  # FAILURE
            response = {
                "state": result.state,
                "status": "エラー",
                "progress": 0,
                "error": str(result.info)
            }
        
        response["server_time"] = datetime.now(timezone.utc).isoformat()
        return jsonify(response)
        
    except Exception as e:
        current_app.logger.error(f"Failed to get task result: {e}")
        return jsonify({
            "state": "ERROR",
            "status": "タスク結果の取得に失敗しました",
            "error": str(e),
            "server_time": datetime.now(timezone.utc).isoformat()
        }), 500
