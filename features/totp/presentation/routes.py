"""TOTP 画面のルーティング"""
from __future__ import annotations

from flask import render_template

from core.models.authz import require_perms

from . import bp


@bp.route("/")
@require_perms("totp:view")
def index():
    return render_template("totp/index.html")
