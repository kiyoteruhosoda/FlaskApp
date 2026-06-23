"""機密値マスキング付きの外向き HTTP リクエスト送信ユーティリティ。

リクエスト／レスポンスをアプリケーションロガーへ記録しつつ ``requests`` で
送信する共通処理。複数の bounded context（certs / photonest など）から利用される
ため、特定の presentation 層ではなく共有 infrastructure 層に置く。

``current_app.logger`` には依存するが、Flask アプリ生成や Blueprint には依存しない。
"""

from __future__ import annotations

import json as _json
from collections.abc import Mapping, Sequence
from typing import Any, Callable

import requests
from flask import current_app

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


__all__ = [
    "log_requests_and_send",
    "MASKED_VALUE",
    "SENSITIVE_HEADER_KEYS",
    "SENSITIVE_BODY_KEYS",
]
