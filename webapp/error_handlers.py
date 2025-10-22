"""Centralized HTTP error handling for HTML requests."""
from flask import current_app, flash, jsonify, redirect, request, url_for
from flask_babel import gettext as _
from werkzeug.exceptions import default_exceptions


def _is_api_request() -> bool:
    """Return True when the current request targets the API."""
    path = request.path or ""
    return path == "/api" or path.startswith("/api/")


def _handle_html_error(error, *, is_server_error: bool):
    """Return a redirect response for HTML errors while logging appropriately."""

    code = getattr(error, "code", 500 if is_server_error else 400)

    if _is_api_request():
        message = (
            _("Internal Server Error")
            if is_server_error
            else getattr(error, "description", "Unexpected error")
        )
        return (
            jsonify(
                {
                    "status": "error",
                    "code": code,
                    "message": message,
                }
            ),
            code,
        )

    logger = current_app.logger.error if is_server_error else current_app.logger.warning
    log_kwargs = {"exc_info": error} if is_server_error else {}
    logger("%s %s (%s)", code, request.path, request.remote_addr, **log_kwargs)

    if is_server_error:
        flash(_("An unexpected error occurred. Please try again later."), "error")

    response = redirect(url_for("index"))
    response.status_code = code
    return response


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

    for status_code in default_exceptions:
        if 500 <= status_code < 600:
            app.register_error_handler(status_code, handle_server_errors)

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

