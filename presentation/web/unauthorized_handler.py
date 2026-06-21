"""未認証アクセス時のハンドラ（診断ログ＋ログイン誘導）.

``create_app()`` に定義されていた Flask-Login の ``unauthorized_handler`` を切り出す。
セッション状態の診断・構造化ログ出力・API/HTML に応じた応答という責務を担う。
ログイン状態の分類は副作用のない純粋関数として分離し、単体テスト可能にする。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)
from flask_babel import gettext as _


def classify_login_state(session_info: Dict[str, Any]) -> str:
    """セッション診断情報から未認証となった理由を分類する。"""

    if not session_info["cookie_present"]:
        return "session_cookie_missing"
    if not session_info["user_id_present"]:
        return "session_cookie_without_user_id"
    if session_info["fresh_login"] is False:
        return "session_not_fresh"
    return "unknown"


def register_unauthorized_handler(app: Flask, login_manager) -> None:
    """Flask-Login の未認証ハンドラを登録する。"""

    @login_manager.unauthorized_handler
    def unauthorized():
        existing_request_id = getattr(g, "request_id", None)
        request_id = existing_request_id or str(uuid4())
        if existing_request_id is None:
            g.request_id = request_id

        raw_user_id = session.get("_user_id")
        user_hash = None
        if raw_user_id is not None:
            user_hash = hashlib.sha256(str(raw_user_id).encode("utf-8")).hexdigest()

        forwarded_for = request.headers.get("X-Forwarded-For")
        client_ip = None
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        if not client_ip:
            client_ip = request.remote_addr

        session_cookie_name = app.config.get("SESSION_COOKIE_NAME", "session")
        session_cookie_value = request.cookies.get(session_cookie_name)
        session_info = {
            "cookie_name": session_cookie_name,
            "cookie_present": session_cookie_value is not None,
            "session_new": getattr(session, "new", None),
            "session_permanent": session.permanent,
            "fresh_login": session.get("_fresh"),
            "remember_token_present": "_remember" in session,
            "user_id_present": raw_user_id is not None,
        }

        login_state = classify_login_state(session_info)

        diagnostics = {
            "login_state": login_state,
            "session_keys": sorted(key for key in session.keys()),
        }

        log_payload = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "id": request_id,
            "event": "auth.unauthorized",
            "message": "Redirected to login due to unauthorized access.",
            "user": {
                "id_hash": user_hash,
                "is_authenticated": raw_user_id is not None,
            },
            "request": {
                "method": request.method,
                "path": request.path,
                "full_path": request.full_path,
                "ip": client_ip,
                "forwarded_for": forwarded_for,
                "user_agent": request.user_agent.string,
            },
            "session": session_info,
            "diagnostics": diagnostics,
        }

        app.logger.warning(
            json.dumps(log_payload, ensure_ascii=False),
            extra={
                "event": "auth.unauthorized",
                "path": request.path,
                "request_id": request_id,
            },
        )

        wants_json = (
            request.is_json
            or request.accept_mimetypes.best_match(["application/json", "text/html"]) == "application/json"
        )
        is_ajax = wants_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"

        if is_ajax:
            response_payload = {
                "status": "error",
                "error": "unauthorized",
                "message": _("Please log in to access this page."),
                "login_state": login_state,
            }
            response = jsonify(response_payload)
            response.status_code = 401
            response.headers["X-Session-Expired"] = "1"
            return response

        # i18nメッセージを自分で出す（カテゴリも自由）
        flash(_("Please log in to access this page."), "error")
        # 元のURLへ戻れるよう next を付ける
        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for("auth.login", next=next_url))
