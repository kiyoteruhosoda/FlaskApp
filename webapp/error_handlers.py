"""Centralized HTTP error handling for HTML requests."""
from importlib import import_module

from flask import current_app, flash, jsonify, redirect, request, url_for
from flask_babel import gettext as _, get_locale
from werkzeug.exceptions import InternalServerError, default_exceptions


def _localize_message(message: str) -> str:
    translated = _(message)
    if translated != message:
        return translated

    try:
        webapp_module = import_module("webapp")
    except ModuleNotFoundError:  # pragma: no cover - defensive fallback
        return message

    translate_fn = getattr(webapp_module, "_translate_message", None)
    if callable(translate_fn):
        return translate_fn(message)

    return message


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
            message_key = getattr(error, "name", "Internal Server Error") or "Internal Server Error"
            payload = {
                "status": "error",
                "code": code,
                "message": _localize_message(message_key),
            }
            logger = current_app.logger.error
            log_kwargs = {"exc_info": error}
        else:
            message_key = getattr(error, "name", "Error")
            payload = {
                "status": "error",
                "code": code,
                "message": _localize_message(message_key),
            }
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

