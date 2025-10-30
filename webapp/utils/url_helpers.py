from __future__ import annotations

"""Helpers for building externally visible URLs."""

from flask import Request, request

from core.settings import settings


def _extract_forwarded_proto(forwarded_header: str | None) -> str | None:
    """Parse the ``Forwarded`` header and return the ``proto`` value if present."""

    if not forwarded_header:
        return None

    for part in forwarded_header.split(","):
        for attribute in part.split(";"):
            attribute = attribute.strip()
            if attribute.lower().startswith("proto="):
                value = attribute.split("=", 1)[1].strip().strip('"')
                if value:
                    return value.strip().lower()
    return None


def _extract_x_forwarded_proto(header_value: str | None) -> str | None:
    """Return the first protocol value from ``X-Forwarded-Proto`` if available."""

    if not header_value:
        return None

    proto = header_value.split(",")[0].strip()
    if proto:
        return proto.lower()
    return None


def determine_external_scheme(req: Request | None = None) -> str:
    """Return the preferred scheme when generating external URLs.

    The resolution order matches production expectations:

    1. Persisted application setting ``PREFERRED_URL_SCHEME`` (manual override).
    2. ``Forwarded`` header ``proto`` attribute.
    3. ``X-Forwarded-Proto`` header.
    4. The request's ``scheme``/``wsgi.url_scheme``.
    5. Fallback to ``https`` to avoid downgrading OAuth redirects.
    """

    req = req or request

    preferred_scheme = settings.preferred_url_scheme
    if preferred_scheme:
        scheme = str(preferred_scheme).strip().lower()
        if scheme:
            return scheme

    forwarded_proto = _extract_forwarded_proto(req.headers.get("Forwarded"))
    if forwarded_proto:
        return forwarded_proto

    x_forwarded_proto = _extract_x_forwarded_proto(req.headers.get("X-Forwarded-Proto"))
    if x_forwarded_proto:
        return x_forwarded_proto

    env_scheme = getattr(req, "scheme", None) or req.environ.get("wsgi.url_scheme")
    if env_scheme:
        return str(env_scheme).strip().lower()

    return "https"


__all__ = ["determine_external_scheme"]
