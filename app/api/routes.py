from datetime import datetime
import json
import secrets
from urllib.parse import urlencode

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
from ..models.google_account import GoogleAccount




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
    return jsonify({"auth_url": auth_url, "server_time": datetime.utcnow().isoformat()})



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
