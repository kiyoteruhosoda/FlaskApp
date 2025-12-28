"""証明書API用Blueprint"""
from __future__ import annotations

from flask import Blueprint

certs_api_bp = Blueprint("certs_api", __name__)

from . import routes  # noqa: E402,F401

__all__ = ["certs_api_bp"]
