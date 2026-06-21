"""アプリ設定に基づく CORS（Cross-Origin Resource Sharing）制御を担う。

``create_app()`` に同居していた CORS ロジックをここへ集約する。許可オリジンの
判定とレスポンスヘッダ付与という純粋・準純粋なロジックを公開関数として切り出し、
Flask フックへの登録のみ ``configure_cors(app)`` が担う。これにより許可判定を
リクエストコンテキストなしで単体テストできる。
"""

from __future__ import annotations

from typing import Optional, Sequence

from flask import Flask, make_response, request

from core.settings import settings


DEFAULT_CORS_ALLOW_HEADERS = "Authorization,Content-Type"
DEFAULT_CORS_ALLOW_METHODS = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
DEFAULT_CORS_MAX_AGE = "86400"


def allowed_origins_from_settings() -> tuple[str, ...]:
    """設定値から空要素を除いた許可オリジンのタプルを返す。"""

    config_value = settings.cors_allowed_origins
    return tuple(value for value in config_value if value)


def is_origin_allowed(origin: Optional[str], allowed_origins: Sequence[str]) -> bool:
    """指定オリジンが許可リスト（ワイルドカード含む）に該当するかを判定する。"""

    if not origin:
        return False
    if not allowed_origins:
        return False
    if "*" in allowed_origins:
        return True
    return origin in allowed_origins


def apply_base_headers(response, origin: str, allowed_origins: Sequence[str]) -> None:
    """許可オリジンに応じた基本 CORS ヘッダをレスポンスへ付与する。"""

    if "*" in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = "*"
    else:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers.add("Vary", "Origin")
        response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers.setdefault("Access-Control-Max-Age", DEFAULT_CORS_MAX_AGE)


def configure_cors(app: Flask) -> None:
    """アプリ設定に基づき CORS のプリフライト/レスポンスフックを登録する。"""

    def _current_allowed_origins() -> tuple[str, ...]:
        origins = allowed_origins_from_settings()
        app.config["CORS_ALLOWED_ORIGINS"] = origins
        return origins

    @app.before_request
    def _handle_cors_preflight():
        if request.method != "OPTIONS":
            return None
        origin = request.headers.get("Origin")
        allowed_origins = _current_allowed_origins()
        if not is_origin_allowed(origin, allowed_origins):
            return None

        response = make_response("", 204)
        apply_base_headers(response, origin or "", allowed_origins)

        requested_method = request.headers.get("Access-Control-Request-Method")
        response.headers["Access-Control-Allow-Methods"] = (
            requested_method or DEFAULT_CORS_ALLOW_METHODS
        )

        requested_headers = request.headers.get("Access-Control-Request-Headers")
        if requested_headers:
            response.headers["Access-Control-Allow-Headers"] = requested_headers
        else:
            response.headers["Access-Control-Allow-Headers"] = DEFAULT_CORS_ALLOW_HEADERS

        return response

    @app.after_request
    def _apply_cors_headers(response):
        origin = request.headers.get("Origin")
        allowed_origins = _current_allowed_origins()
        if not is_origin_allowed(origin, allowed_origins):
            return response

        apply_base_headers(response, origin or "", allowed_origins)

        if "Access-Control-Allow-Methods" not in response.headers:
            response.headers["Access-Control-Allow-Methods"] = DEFAULT_CORS_ALLOW_METHODS

        request_headers = request.headers.get("Access-Control-Request-Headers")
        if request_headers:
            response.headers["Access-Control-Allow-Headers"] = request_headers
        elif "Access-Control-Allow-Headers" not in response.headers:
            response.headers["Access-Control-Allow-Headers"] = DEFAULT_CORS_ALLOW_HEADERS

        return response
