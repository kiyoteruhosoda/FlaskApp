"""Centralized HTTP error handling for HTML requests."""
import json

from flask import current_app, flash, g, jsonify, redirect, request, url_for
from flask_babel import gettext as _, get_locale
from werkzeug.exceptions import InternalServerError, default_exceptions

from presentation.web.templating.translation import translate_message


def _localize_message(message: str) -> str:
    return translate_message(message)


def _is_api_request() -> bool:
    """Return True when the current request targets the API."""
    path = request.path or ""
    return path == "/api" or path.startswith("/api/")


def _handle_html_error(error, *, is_server_error: bool):
    """Return a redirect response for HTML errors while logging appropriately."""

    code = getattr(error, "code", 500 if is_server_error else 400)

    if _is_api_request():
        locale = str(get_locale() or current_app.config.get("BABEL_DEFAULT_LOCALE", "en"))

        if is_server_error:
            message_key = getattr(error, "name", "Internal Server Error")
            payload = {
                "status": "error",
                "code": code,
                "message": _localize_message(message_key),
            }
            logger = current_app.logger.error
            log_kwargs = {"exc_info": error}
        else:
            message_key = getattr(error, "name", "Error")
            localized_message = _localize_message(message_key)
            
            # デバッグ情報を追加
            payload = {
                "status": "error",
                "code": code,
                "message": localized_message,
                "error": localized_message,
            }
            
            # Flask-Smorestのバリデーションエラーの詳細情報を追加
            if hasattr(error, 'data') and error.data:
                payload['validation_errors'] = error.data
                current_app.logger.error(f"Validation errors: {error.data}")
            
            # リクエスト情報をログに出力
            current_app.logger.error(f"API Error - Method: {request.method}, Path: {request.path}")
            current_app.logger.error(f"Request Headers: {dict(request.headers)}")
            if request.is_json:
                current_app.logger.error(f"Request JSON: {request.get_json()}")
            elif request.form:
                current_app.logger.error(f"Request Form: {dict(request.form)}")
            
            logger = current_app.logger.warning
            log_kwargs = {}

        logger("%s %s (%s)", code, request.path, request.remote_addr, **log_kwargs)

        response = jsonify(payload)
        response.status_code = code
        response.headers["Content-Language"] = locale
        return response

    logger = current_app.logger.error if is_server_error else current_app.logger.warning
    log_kwargs = {"exc_info": error} if is_server_error else {}
    logger("%s %s (%s)", code, request.path, request.remote_addr, **log_kwargs)

    if is_server_error:
        flash(_("An unexpected error occurred. Please try again later."), "error")

    return redirect(url_for("index"))


def register_error_handlers(app):
    """Register global error handlers for HTML responses.

    API endpoints keep returning JSON errors as before.
    """

    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(405)
    @app.errorhandler(422)  # Unprocessable Entityを追加
    def handle_client_errors(error):
        """Handle 4xx errors by redirecting to the top page."""

        return _handle_html_error(error, is_server_error=False)

    def handle_server_errors(error):
        """Handle 5xx errors by redirecting to the top page."""

        return _handle_html_error(error, is_server_error=True)

    server_error_status_codes = [
        status_code for status_code in default_exceptions if 500 <= status_code < 600
    ]

    for status_code in server_error_status_codes:
        app.register_error_handler(status_code, handle_server_errors)

    app.register_error_handler(InternalServerError, handle_server_errors)

    @app.errorhandler(401)
    def handle_unauthorized(error):
        """Handle authentication failures by redirecting to the login page."""
        if _is_api_request():
            return (
                jsonify(
                    {
                        "status": "unauthorized",
                        "code": 401,
                        "message": "Authentication required.",
                    }
                ),
                401,
            )

        current_app.logger.info("401 %s -> redirect login", request.path)
        return redirect(url_for("auth.login"))


def register_debug_error_handlers(app):
    """422/500 の詳細ログ付きハンドラを登録する。

    ``register_error_handlers`` の後に呼ぶことで、422/500 についてはこちらの
    ハンドラが優先される（Flask はコード単位で後勝ち）。500 の Flask 既定例外
    ログも抑制し、構造化ログとの二重出力を防ぐ。
    """

    @app.errorhandler(422)
    def handle_validation_error(e):
        """Marshmallow validation errors (422 Unprocessable Entity) のデバッグ強化"""
        import traceback

        app.logger.error("422 Validation Error occurred:")
        app.logger.error(f"Request path: {request.path}")
        app.logger.error(f"Request method: {request.method}")
        app.logger.error(f"Request headers: {dict(request.headers)}")
        app.logger.error(f"Request args: {request.args.to_dict()}")

        try:
            request_json = request.get_json(force=True)
            app.logger.error(f"Request JSON: {request_json}")
        except Exception as json_error:
            app.logger.error(f"Failed to parse request JSON: {json_error}")
            app.logger.error(f"Raw request data: {request.data}")

        app.logger.error(f"Exception details: {e}")
        app.logger.error(f"Exception type: {type(e)}")
        if hasattr(e, 'description'):
            app.logger.error(f"Exception description: {e.description}")
        if hasattr(e, 'data'):
            app.logger.error(f"Exception data: {e.data}")

        # Traceback も出力
        app.logger.error(f"Traceback:\n{traceback.format_exc()}")

        # デフォルトのFlask-Smorest処理に委任
        # webargs の e.data には非シリアライズ可能な Schema インスタンスが
        # 含まれる場合があるため、messages のみを details として返す。
        error_data = getattr(e, 'data', None) or {}
        return {"error": "validation_failed", "message": str(e), "details": error_data.get('messages', {})}, 422

    @app.errorhandler(500)
    def handle_internal_server_error(e):
        """500 Internal Server Error を1件の構造化ログとして記録する。

        元例外のメッセージ・リクエストパス・トレースバックを単一の Log
        エントリにまとめる。Flask 既定の例外ログ（log_exception）は下で
        抑制しているため、500 についてはこのハンドラが唯一の記録元となる。
        """
        original = getattr(e, "original_exception", None)
        exc = original if original is not None else e

        # api.server_error の after_request ログと二重化しないよう印を付ける
        g.exception_logged = True

        app.logger.error(
            json.dumps({"message": str(exc), "status": 500}, ensure_ascii=False),
            exc_info=True,
            extra={
                "event": "api.server_error",
                "path": request.path,
                "request_id": getattr(g, "request_id", None),
            },
        )

        # メッセージをロケールに合わせて翻訳し、Content-Language を付与する
        locale = str(get_locale() or app.config.get("BABEL_DEFAULT_LOCALE", "en"))
        response = jsonify(
            {"error": "internal_server_error", "message": _("Internal Server Error")}
        )
        response.status_code = 500
        response.headers["Content-Language"] = locale
        return response

    def _log_exception_via_handler(exc_info):
        """Flask 既定の例外ログを抑制する。

        500 は handle_internal_server_error が構造化ログとして記録するため、
        Flask が出力する "Exception on ..." の重複ログを抑える。
        """
        return None

    app.log_exception = _log_exception_via_handler

