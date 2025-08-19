import json
from datetime import datetime, timezone
from flask import current_app
import requests

from ..extensions import db
from core.crypto import encrypt, decrypt


class RefreshTokenError(Exception):
    """Error occurred while refreshing OAuth token."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def log_requests_and_send(
    method,
    url,
    *,
    headers=None,
    params=None,
    data=None,
    json_data=None,
    timeout=10,
):
    """requestsリクエスト・レスポンスをlogに記録して送信する共通関数"""
    import json as _json

    # 送信前ログ
    current_app.logger.info(
        _json.dumps(
            {
                "method": method,
                "headers": dict(headers) if headers else None,
                "params": params,
                "data": data,
                "json": json_data,
            },
            ensure_ascii=False,
        ),
        extra={"event": "requests.send", "path": url},
    )

    # 実リクエスト
    req_func = getattr(requests, method.lower())
    res = req_func(
        url,
        headers=headers,
        params=params,
        data=data,
        json=json_data,
        timeout=timeout,
    )

    # 受信後ログ
    try:
        res_body = res.json()
    except Exception:
        res_body = res.text
    current_app.logger.info(
        _json.dumps(
            {
                "status_code": res.status_code,
                "headers": dict(res.headers) if hasattr(res, "headers") else None,
                "body": res_body,
            },
            ensure_ascii=False,
        ),
        extra={"event": "requests.recv", "path": url},
    )
    return res


def refresh_google_token(account):
    """Refresh Google OAuth token and update the account."""
    tokens = json.loads(decrypt(account.oauth_token_json) or "{}")
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RefreshTokenError("no_refresh_token", 400)

    data = {
        "client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
        "client_secret": current_app.config.get("GOOGLE_CLIENT_SECRET"),
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
