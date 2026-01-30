"""Utility helpers for managing the GUI access cookie."""
from __future__ import annotations

from typing import Any, Iterable

from flask import current_app, request

from core.settings import settings
from webapp.utils import determine_external_scheme

GUI_ACCESS_COOKIE_NAME = "access_token"
GUI_VIEW_SCOPE = "gui:view"
API_LOGIN_SCOPE_SESSION_KEY = "api_login_granted_scope"

_LOCAL_HTTP_HOSTS = {"localhost", "127.0.0.1", "::1"}


def normalize_scope_items(items: Iterable[str]) -> list[str]:
    normalized: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        token = item.strip()
        if token:
            normalized.add(token)
    return sorted(normalized)


def should_issue_gui_access_cookie(scope_items: Iterable[str]) -> bool:
    for item in scope_items:
        if isinstance(item, str) and item.strip() == GUI_VIEW_SCOPE:
            return True
    return False


def _resolve_secure_cookie_flag() -> bool:
    """Decide whether GUI cookies should be marked as ``Secure``."""

    configured_secure = settings.session_cookie_secure
    scheme = determine_external_scheme(request)

    if configured_secure:
        if scheme == "https":
            return True

        host = (request.host or "").split(":", 1)[0].lower()
        if host in _LOCAL_HTTP_HOSTS or current_app.debug or current_app.testing or settings.testing:
            current_app.logger.debug(
                "Downgrading GUI cookie Secure flag for local HTTP request.",
                extra={"event": "auth.cookie.insecure", "host": host, "scheme": scheme},
            )
            return False

        return True

    return scheme == "https"


def gui_access_cookie_options() -> tuple[dict[str, Any], dict[str, Any]]:
    secure_flag = _resolve_secure_cookie_flag()
    set_options: dict[str, Any] = {
        "httponly": True,
        "secure": secure_flag,
    }
    delete_options: dict[str, Any] = {"secure": secure_flag}

    config = current_app.config
    same_site = config.get("SESSION_COOKIE_SAMESITE", "Lax")
    if same_site:
        set_options["samesite"] = same_site

    path = config.get("SESSION_COOKIE_PATH", "/")
    if path:
        set_options["path"] = path
        delete_options["path"] = path

    domain = config.get("SESSION_COOKIE_DOMAIN")
    if domain:
        set_options["domain"] = domain
        delete_options["domain"] = domain

    return set_options, delete_options


def clear_gui_access_cookie(response) -> None:
    _, delete_options = gui_access_cookie_options()
    response.delete_cookie(GUI_ACCESS_COOKIE_NAME, **delete_options)


def apply_gui_access_cookie(
    response,
    access_token: str | None,
    scope_items: Iterable[str],
) -> None:
    normalized_scope = normalize_scope_items(scope_items)
    if not access_token or not should_issue_gui_access_cookie(normalized_scope):
        clear_gui_access_cookie(response)
        return

    set_options, _ = gui_access_cookie_options()
    response.set_cookie(
        GUI_ACCESS_COOKIE_NAME,
        access_token,
        **set_options,
    )
