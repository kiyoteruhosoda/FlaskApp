"""API リクエスト/レスポンスの構造化ロギングと requestId 付与（FastAPI）。

Flask 版 ``presentation/web/middleware/request_logging.py`` の後継。

- すべてのリクエストに requestId を発行し、処理中に出力される全ログへ
  自動付与する（``RequestIdLogFilter`` が contextvar から補完する）。
- ``/api`` パスの入出力を構造化ログ（``api.input`` / ``api.output``）として
  記録する。
- 未処理例外は必ず traceback 付きで ``api.error`` として記録してから
  再送出する（グローバルハンドラが 500 応答を返す）。
"""
from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from shared.kernel.logging.request_context import bind_request_id, reset_request_id

logger = logging.getLogger(__name__)

_MASKED_VALUE = "***"
_SENSITIVE_QUERY_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "code",
    "client_secret",
    "password",
    "secret",
    "api_key",
}


def _masked_query_params(request: Request) -> dict[str, str]:
    return {
        key: _MASKED_VALUE if key.lower() in _SENSITIVE_QUERY_KEYS else value
        for key, value in request.query_params.items()
    }


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """requestId の発行と API 入出力・エラーの構造化ロギングを行う。"""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        context_token = bind_request_id(request_id)

        path = request.url.path
        is_api = path.startswith("/api")
        started = time.perf_counter()

        try:
            if is_api:
                input_payload: dict = {
                    "method": request.method,
                    "path": path,
                    "requestId": request_id,
                }
                query = _masked_query_params(request)
                if query:
                    input_payload["query"] = query
                logger.info(
                    json.dumps(input_payload, ensure_ascii=False),
                    extra={"event": "api.input", "request_id": request_id, "path": path},
                )

            try:
                response = await call_next(request)
            except Exception as exc:
                # API/Worker 以外の経路（SPA 配信等）も含め、未処理例外は
                # 必ず traceback 付きで DB ログへ残す。応答の生成は
                # グローバル例外ハンドラに委ねる。
                logger.error(
                    json.dumps(
                        {
                            "method": request.method,
                            "path": path,
                            "requestId": request_id,
                            "durationMs": int((time.perf_counter() - started) * 1000),
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                        ensure_ascii=False,
                        default=str,
                    ),
                    extra={
                        "event": "api.error" if is_api else "request.error",
                        "request_id": request_id,
                        "path": path,
                    },
                    exc_info=True,
                )
                raise

            if is_api:
                output_payload = {
                    "method": request.method,
                    "path": path,
                    "status": response.status_code,
                    "requestId": request_id,
                    "durationMs": int((time.perf_counter() - started) * 1000),
                }
                if response.status_code >= 500:
                    log_callable = logger.error
                elif response.status_code >= 400:
                    log_callable = logger.warning
                else:
                    log_callable = logger.info
                log_callable(
                    json.dumps(output_payload, ensure_ascii=False),
                    extra={"event": "api.output", "request_id": request_id, "path": path},
                )
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            reset_request_id(context_token)


__all__ = ["RequestLoggingMiddleware"]
