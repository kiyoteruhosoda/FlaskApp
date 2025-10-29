"""Utility helpers for managing the GUI access cookie."""
from __future__ import annotations

from typing import Any, Iterable

from flask import current_app

from core.settings import settings

GUI_ACCESS_COOKIE_NAME = "access_token"
GUI_VIEW_SCOPE = "gui:view"
API_LOGIN_SCOPE_SESSION_KEY = "api_login_granted_scope"


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


def gui_access_cookie_options() -> tuple[dict[str, Any], dict[str, Any]]:
    set_options: dict[str, Any] = {
        "httponly": True,
        "secure": settings.session_cookie_secure,
    }
    delete_options: dict[str, Any] = {}

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
