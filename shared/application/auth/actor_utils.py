"""Utility helpers for resolving the current actor identifier."""
from __future__ import annotations

from flask_login import current_user


def _normalize_identifier(value: object) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed:
            return trimmed
    return None


def resolve_actor_identifier() -> str:
    """Return a stable identifier for the current actor.

    The resolution order is::

        subject_id > get_id() > display_name > "unknown"
    """

    user = current_user

    subject_id = _normalize_identifier(getattr(user, "subject_id", None))
    if subject_id:
        return subject_id

    if hasattr(user, "get_id"):
        identifier = _normalize_identifier(user.get_id())
        if identifier:
            return identifier

    display_name = _normalize_identifier(getattr(user, "display_name", None))
    if display_name:
        return display_name

    return "unknown"


__all__ = ["resolve_actor_identifier"]
