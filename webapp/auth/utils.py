import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Callable

from flask import current_app

from core.settings import settings
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
    request_payload = {
        "method": method,
        "headers": _mask_sensitive_values(dict(headers)) if headers else None,
        "params": _mask_sensitive_values(params),
        "data": _mask_sensitive_values(data),
        "json": _mask_sensitive_values(json_data),
    }
    current_app.logger.info(
        _json.dumps(request_payload, ensure_ascii=False, default=str),
        extra={"event": "requests.send", "path": url},
    )

    # 実リクエスト
    if not isinstance(method, str):
        raise ValueError("HTTP method must be a string")
    normalized_method = method.strip().lower()
    if normalized_method == "get":
        req_func: Callable[..., requests.Response] = requests.get
    elif normalized_method == "post":
        req_func = requests.post
    elif normalized_method == "put":
        req_func = requests.put
    elif normalized_method == "delete":
        req_func = requests.delete
    elif normalized_method == "patch":
        req_func = requests.patch
    elif normalized_method == "head":
        req_func = requests.head
    elif normalized_method == "options":
        req_func = requests.options
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")
    try:
        res = req_func(
            url,
            headers=headers,
            params=params,
            data=data,
            json=json_data,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        error_payload = {
            "error": str(exc),
            "method": method,
            "params": _mask_sensitive_values(params),
            "data": _mask_sensitive_values(data),
            "json": _mask_sensitive_values(json_data),
        }
        current_app.logger.error(
            _json.dumps(error_payload, ensure_ascii=False, default=str),
            extra={"event": "requests.error", "path": url},
            exc_info=True,
        )
        raise

    # 受信後ログ
    try:
        res_body = res.json()
    except Exception:
        res_body = res.text
    try:
        response_headers = dict(res.headers)
    except AttributeError:
        response_headers = None

    response_payload = {
        "status_code": res.status_code,
        "headers": _mask_sensitive_values(response_headers) if response_headers is not None else None,
        "body": _mask_sensitive_values(res_body),
    }
    log_callable = current_app.logger.info
    if res.status_code >= 500:
        log_callable = current_app.logger.error
    elif res.status_code >= 400:
        log_callable = current_app.logger.warning
    log_callable(
        _json.dumps(response_payload, ensure_ascii=False, default=str),
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

MASKED_VALUE = "***"
SENSITIVE_HEADER_KEYS = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "x-api-token",
    "x-auth-token",
    "x-access-token",
    "x-refresh-token",
}
SENSITIVE_BODY_KEYS = {
    "access_token",
    "refresh_token",
    "id_token",
    "token",
}


def _mask_sensitive_values(value: Any):
    """ヘッダーやボディ内の機密値をマスクした新しいオブジェクトを返す"""

    if value is None:
        return None

    if isinstance(value, Mapping):
        masked = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if key_lower in SENSITIVE_HEADER_KEYS or key_lower in SENSITIVE_BODY_KEYS:
                masked[key] = MASKED_VALUE
            else:
                masked[key] = _mask_sensitive_values(item)
        return masked

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if isinstance(value, tuple):
            return tuple(_mask_sensitive_values(item) for item in value)
        return [_mask_sensitive_values(item) for item in value]

    return value
