"""リクエスト内容をそのまま返すAPIエンドポイント。"""
from __future__ import annotations

from flask import Response, jsonify, request

from . import bp


@bp.route(
    "/echo",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
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
)
def echo() -> Response:
    """受信したリクエストのヘッダとボディをまとめて返す。"""
    json_payload = request.get_json(silent=True)
    raw_body = request.get_data(as_text=True)

    response_body = {
        "headers": dict(request.headers),
        "body": raw_body,
        "json": json_payload,
    }

    return jsonify(response_body)
