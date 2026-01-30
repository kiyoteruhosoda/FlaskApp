"""Simple CSRF token helpers backed by the Flask session."""

from __future__ import annotations

import hmac
import secrets
from typing import Final

from flask import session

_CSRF_SESSION_KEY: Final[str] = "_csrf_token"


def get_or_set_csrf_token() -> str:
    """Return the current CSRF token and generate one if necessary."""

    token = session.get(_CSRF_SESSION_KEY)
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_urlsafe(32)
        session[_CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token(token: str | None) -> bool:
    """Validate the given token against the value stored in the session."""

    if not token:
        return False

    stored_token = session.get(_CSRF_SESSION_KEY)
    if not isinstance(stored_token, str):
        return False

    return hmac.compare_digest(stored_token, token)
