"""Utility helpers for resolving and converting time zones."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def resolve_timezone(
    tz_name: Optional[str], fallback: Optional[str] = "UTC"
) -> Tuple[str, ZoneInfo]:
    """Resolve a time zone name to a :class:`ZoneInfo` instance.

    Parameters
    ----------
    tz_name:
        Preferred time zone identifier (e.g. ``"Asia/Tokyo"``). ``None`` or an
        empty string is treated as missing.
    fallback:
        Secondary identifier that should be tried when *tz_name* cannot be
        resolved. Defaults to ``"UTC"``. When *fallback* cannot be resolved
        either, ``("UTC", ZoneInfo("UTC"))`` is returned.

    Returns
    -------
    tuple
        A tuple ``(resolved_name, zoneinfo)`` where *resolved_name* is the
        identifier that successfully resolved, ensuring callers can persist the
        canonical value.
    """

    candidates = [tz_name, fallback, "UTC"]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return candidate, ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            continue
    # Fallback: ZoneInfo always provides UTC, but guard just in case
    return "UTC", timezone.utc


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize *dt* to an aware UTC datetime."""

    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def convert_to_timezone(
    dt: Optional[datetime], tzinfo: ZoneInfo
) -> Optional[datetime]:
    """Convert *dt* (assumed UTC) into *tzinfo* while handling ``None`` values."""

    normalized = ensure_utc(dt)
    if normalized is None:
        return None
    return normalized.astimezone(tzinfo)


utc = timezone.utc

__all__ = [
    "resolve_timezone",
    "ensure_utc",
    "convert_to_timezone",
    "utc",
]
