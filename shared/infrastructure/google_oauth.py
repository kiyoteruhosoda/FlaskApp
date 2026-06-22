"""Google OAuth トークン更新ユーティリティ。

Google Photos 連携アカウントの OAuth トークンを更新する処理。複数の
bounded context（photonest / picker_import など）から利用されるため、特定の
presentation 層ではなく共有 infrastructure 層に置く。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from shared.kernel.crypto.crypto import decrypt, encrypt
from shared.kernel.database.db import db
from shared.kernel.settings.settings import settings
from shared.infrastructure.http_logging import log_requests_and_send


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


__all__ = ["RefreshTokenError", "refresh_google_token"]
