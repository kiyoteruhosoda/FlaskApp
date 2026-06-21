"""リクエスト内容をそのまま返すAPIエンドポイント。"""
from __future__ import annotations

from flask import Response, request

from . import bp
from .routes import login_or_jwt_required


def _build_request_target() -> str:
    """クエリ文字列を含むリクエストターゲットを生成する。"""

    query_string = request.query_string.decode("utf-8", "replace")
    if query_string:
        return f"{request.path}?{query_string}"
    return request.path


def _format_request_as_plain_text() -> str:
    """HTTPリクエスト形式のプレーンテキストを生成する。"""

    protocol = request.environ.get("SERVER_PROTOCOL", "HTTP/1.1")
    request_line = f"{request.method} {_build_request_target()} {protocol}"

    header_lines = [f"{header}: {value}" for header, value in request.headers.items()]

    body = request.get_data(as_text=True)
    sections = [request_line, *header_lines, ""]
    if body:
        sections.append(body)

    return "\r\n".join(sections)


@bp.route(
    "/echo",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
@login_or_jwt_required
@bp.doc(
    methods=["POST", "PUT", "PATCH"],
    requestBody={
        "required": False,
        "description": "Echoes the submitted payload and headers. Useful for testing proxy behaviour.",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "additionalProperties": True,
                    "description": "任意のJSONオブジェクト。フィールド名や型に制限はありません。",
                },
                "example": {"message": "Hello", "count": 1},
            },
            "text/plain": {
                "schema": {
                    "type": "string",
                    "description": "生のテキストボディ。JSON以外を確認したい場合に利用します。",
                },
                "example": "raw body",
            },
        },
    },
    responses={
        200: {
            "description": "Returns the incoming request in raw HTTP message format.",
            "content": {
                "text/plain": {
                    "schema": {
                        "type": "string",
                        "description": "HTTPリクエストメッセージをそのまま表現したテキスト。",
                        "example": (
                            "POST /api/echo HTTP/1.1\r\n"
                            "Content-Type: application/json\r\n"
                            "X-Debug: 1\r\n\r\n"
                            '{"message": "Hello"}'
                        ),
                    }
                }
            },
        }
    },
)
def echo() -> Response:
    """受信したリクエストのヘッダとボディをHTTPメッセージ形式で返す。"""

    response_text = _format_request_as_plain_text()
    return Response(response_text, mimetype="text/plain")
