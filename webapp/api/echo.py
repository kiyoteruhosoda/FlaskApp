"""リクエスト内容をそのまま返すAPIエンドポイント。"""
from __future__ import annotations

from flask import Response, jsonify, request

from . import bp


@bp.route("/echo", methods=["POST"])
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
