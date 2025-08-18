from datetime import datetime, timezone
import json
import secrets
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
from core.crypto import decrypt, encrypt




@bp.post("/google/oauth/start")
@login_required
def google_oauth_start():
    """Start Google OAuth flow by returning an authorization URL."""
    data = request.get_json() or {}
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
    data = request.get_json() or {}
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
    data = request.get_json() or {}
    account_id = data.get("account_id")
    title = data.get("title") or "Select from Google Photos"
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": "picker.create.begin",
                "account_id": account_id,
            }
        )
    )
    if not isinstance(account_id, int):
        return jsonify({"error": "invalid_account"}), 400
    account = GoogleAccount.query.filter_by(id=account_id, status="active").first()
    if not account:
        return jsonify({"error": "not_found"}), 404

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
            current_app.logger.info(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "event": "picker.create.fail",
                        "account_id": account_id,
                    }
                )
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
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "event": "picker.create.fail",
                    "account_id": account_id,
                }
            )
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
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "event": "picker.create.fail",
                    "account_id": account_id,
                }
            )
        )
        return jsonify({"error": "picker_error", "message": str(e)}), 502

    ps = PickerSession(account_id=account.id, status="pending")
    db.session.add(ps)
    db.session.commit()
    ps.session_id = picker_data.get("sessionId") or picker_data.get("name")
    ps.picker_uri = picker_data.get("pickerUri")
    db.session.commit()
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": "picker.create.success",
                "account_id": account_id,
                "picker_session_id": ps.id,
            }
        )
    )
    return jsonify(
        {
            "pickerSessionId": ps.id,
            "sessionId": ps.session_id,
            "pickerUri": ps.picker_uri,
        }
    )


@bp.get("/picker/session/<int:picker_session_id>")
@login_required
def api_picker_session_status(picker_session_id):
    """Return status of a picker session."""
    ps = PickerSession.query.get(picker_session_id)
    if not ps:
        return jsonify({"error": "not_found"}), 404
    account = GoogleAccount.query.get(ps.account_id)
    selected = None
    if account and account.status == "active" and ps.session_id:
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
        except Exception:
            selected = None
    ps.selected_count = selected
    ps.last_polled_at = datetime.now(timezone.utc)
    db.session.commit()
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": "picker.status.get",
                "picker_session_id": picker_session_id,
                "status": ps.status,
            }
        )
    )
    return jsonify(
        {
            "status": ps.status,
            "selectedCount": ps.selected_count,
            "lastPolledAt": ps.last_polled_at.isoformat().replace("+00:00", "Z"),
            "serverTimeRFC1123": formatdate(usegmt=True),
        }
    )


@bp.post("/picker/session/<int:picker_session_id>/import")
@login_required
def api_picker_session_import(picker_session_id):
    """Enqueue import task for picker session."""
    data = request.get_json() or {}
    account_id = data.get("account_id")
    ps = PickerSession.query.get(picker_session_id)
    if not ps or ps.account_id != account_id:
        return jsonify({"error": "not_found"}), 404
    if ps.status in ("imported", "canceled", "expired"):
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "event": "picker.import.suppress",
                    "picker_session_id": picker_session_id,
                    "status": ps.status,
                }
            )
        )
        return jsonify({"error": "already_done"}), 409
    stats = ps.stats()
    if stats.get("celery_task_id"):
        current_app.logger.info(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "event": "picker.import.suppress",
                    "picker_session_id": picker_session_id,
                    "status": ps.status,
                }
            )
        )
        return jsonify({"error": "already_enqueued"}), 409
    task_id = uuid4().hex
    stats["celery_task_id"] = task_id
    ps.set_stats(stats)
    db.session.commit()
    current_app.logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": "picker.import.enqueue",
                "picker_session_id": picker_session_id,
                "status": ps.status,
            }
        )
    )
    return jsonify({"enqueued": True, "celeryTaskId": task_id}), 202
