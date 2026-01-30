"""証明書管理UIのエントリポイント"""
from __future__ import annotations

from flask import Blueprint

certs_ui_bp = Blueprint("certs_ui", __name__, template_folder="templates")

from . import routes  # noqa: E402,F401

__all__ = ["certs_ui_bp"]
