import json
from datetime import datetime, timezone

from core.settings import settings
import requests

from ..bootstrap.extensions import db
from core.crypto import encrypt, decrypt

# 外向き HTTP ロギングユーティリティは共有 infrastructure 層へ移動した。
# 後方互換のため従来の ``from ..auth.utils import log_requests_and_send`` を維持する。
from shared.infrastructure.http_logging import (  # noqa: F401
    MASKED_VALUE,
    SENSITIVE_BODY_KEYS,
    SENSITIVE_HEADER_KEYS,
    _mask_sensitive_values,
    log_requests_and_send,
)


class RefreshTokenError(Exception):
    """Error occurred while refreshing OAuth token."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def refresh_google_token(account):
    """Refresh Google OAuth token and update the account."""
    tokens = json.loads(decrypt(account.oauth_token_json) or "{}")
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RefreshTokenError("no_refresh_token", 400)

    data = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    try:
        res = log_requests_and_send(
            "post", "https://oauth2.googleapis.com/token", data=data, timeout=10
        )
        result = res.json()
        if "error" in result:
            raise RefreshTokenError(result["error"], 400)
    except RefreshTokenError:
        raise
    except Exception as e:  # pragma: no cover - network failure
        raise RefreshTokenError(str(e), 500)

    tokens.update(result)
    account.oauth_token_json = encrypt(json.dumps(tokens))
    account.last_synced_at = datetime.now(timezone.utc)
    db.session.commit()
    return tokens
