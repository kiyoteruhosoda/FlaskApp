"""Time-related helpers.

This module centralizes helpers for obtaining timestamps in UTC.  Returning
timestamps through a single function guarantees that the format stays
consistent across the entire application.
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current UTC time as an aware ``datetime`` instance."""

    return datetime.now(timezone.utc)


def utc_now_isoformat() -> str:
    """Return the current UTC time in ISO 8601 format ending with ``Z``."""

    return utc_now().isoformat().replace("+00:00", "Z")

