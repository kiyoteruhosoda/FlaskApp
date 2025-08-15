from datetime import datetime, timezone
import json

import requests
from flask import current_app, flash, redirect, render_template, url_for
from flask_login import login_required
from flask_babel import gettext as _

from . import bp
from ..extensions import db
from core.models.google_account import GoogleAccount
from core.crypto import decrypt, encrypt
from ..auth.totp import qr_code_data_uri


@bp.get("/picker/<int:account_id>")
@login_required
def picker(account_id: int):
    """Create a Photo Picker session and show its URI as a QR code."""
    account = GoogleAccount.query.get_or_404(account_id)

    tokens = json.loads(decrypt(account.oauth_token_json) or "{}")
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        flash(_("No refresh token available."), "error")
        return redirect(url_for("auth.google_accounts"))

    data = {
        "client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
        "client_secret": current_app.config.get("GOOGLE_CLIENT_SECRET"),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    try:
        res = requests.post("https://oauth2.googleapis.com/token", data=data, timeout=10)
        token_res = res.json()
        if "error" in token_res:
            flash(token_res["error"], "error")
            return redirect(url_for("auth.google_accounts"))
    except Exception as e:  # pragma: no cover - network failure
        flash(str(e), "error")
        return redirect(url_for("auth.google_accounts"))

    access_token = token_res.get("access_token")
    if not access_token:
        flash(_("Failed to obtain access token."), "error")
        return redirect(url_for("auth.google_accounts"))

    tokens.update(token_res)
    account.oauth_token_json = encrypt(json.dumps(tokens))
    account.last_synced_at = datetime.now(timezone.utc)
    db.session.commit()

    try:
        res = requests.post(
            "https://photospicker.googleapis.com/v1/sessions",
            headers={"Authorization": f"Bearer {access_token}"},
            json={},
            timeout=10,
        )
        picker_data = res.json()
    except Exception as e:  # pragma: no cover - network failure
        flash(str(e), "error")
        return redirect(url_for("auth.google_accounts"))

    picker_uri = picker_data.get("pickerUri")
    if not picker_uri:
        flash(_("Failed to create picker session."), "error")
        return redirect(url_for("auth.google_accounts"))

    qr_data = qr_code_data_uri(picker_uri)
    return render_template("photo_view/picker.html", picker_uri=picker_uri, qr_data=qr_data)

