"""Utilities for constructing internal API URLs."""

from __future__ import annotations

import os
from urllib.parse import urljoin

DEFAULT_API_BASE_URL = "http://localhost:5000"


def get_api_base_url() -> str:
    """Return the base URL for internal API requests.

    The value is read from the ``API_BASE_URL`` environment variable and
    defaults to ``http://localhost:5000`` when the variable is not set.  The
    trailing slash, if present, is removed to keep the base consistent.
    """

    base_url = os.environ.get("API_BASE_URL", DEFAULT_API_BASE_URL)
    return base_url.rstrip("/")


def build_api_url(path: str) -> str:
    """Return a full URL for the given API path.

    Parameters
    ----------
    path:
        Relative path (with or without a leading slash) that should be appended
        to the configured base URL.
    """

    base = get_api_base_url()
    # ``urljoin`` requires the base to end with a slash to treat the second
    # argument as a relative path.
    return urljoin(f"{base}/", path.lstrip("/"))


__all__ = ["DEFAULT_API_BASE_URL", "get_api_base_url", "build_api_url"]
