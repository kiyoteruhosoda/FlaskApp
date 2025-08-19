"""Utility functions for Google Photos Picker sessions."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Dict, Optional

import requests
from flask import current_app

from core.crypto import decrypt, encrypt
from core.db import db
from core.models.google_account import GoogleAccount


class PickerSessionError(Exception):
    """Error raised when creating a picker session fails."""

    def __init__(self, code: str, message: Optional[str] = None):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def create_picker_session(
    account: GoogleAccount, *, title: Optional[str] = None
) -> Dict[str, object]:
    """Create a Google Photos Picker session for the given account.

    The account's OAuth token is refreshed and the picker session is created.
    On success the parsed JSON response from the picker API is returned.
    """

    tokens = json.loads(decrypt(account.oauth_token_json) or "{}")
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise PickerSessionError("no_refresh_token")

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
        token_res.raise_for_status()
        token_data = token_res.json()
    except requests.RequestException as e:
        raise PickerSessionError("oauth_error", str(e)) from e

    if "access_token" not in token_data:
        raise PickerSessionError(
            token_data.get("error", "oauth_error"),
            token_data.get("error_description"),
        )

    access_token = token_data["access_token"]
    tokens.update(token_data)
    account.oauth_token_json = encrypt(json.dumps(tokens))
    account.last_synced_at = datetime.now(timezone.utc)
    db.session.commit()

    headers = {"Authorization": f"Bearer {access_token}"}
    body = {"title": title} if title else {}
    try:
        picker_res = requests.post(
            "https://photospicker.googleapis.com/v1/sessions",
            json=body,
            headers=headers,
            timeout=15,
        )
        picker_res.raise_for_status()
        picker_data = picker_res.json()
    except requests.RequestException as e:
        raise PickerSessionError("picker_error", str(e)) from e

    return picker_data


__all__ = ["create_picker_session", "PickerSessionError"]

