"""Maintenance API endpoints protected by service account JWTs."""
from __future__ import annotations

from flask import jsonify
from .blueprint import AuthEnforcedBlueprint

from . import bp
from ..auth.service_account_auth import require_service_account_scopes

maintenance_bp = AuthEnforcedBlueprint(
    "maintenance_api", __name__, url_prefix="/maintenance"
)


def _default_audience(req) -> str:
    base = req.url_root.rstrip("/")
    return f"{base}/api/maintenance"


@maintenance_bp.route("/ping", methods=["GET"])
@require_service_account_scopes(["maintenance:read"], audience=_default_audience)
def maintenance_ping():
    from flask import g

    account = getattr(g, "service_account", None)
    return (
        jsonify(
            {
                "status": "ok",
                "service_account": account.name if account else None,
            }
        ),
        200,
    )


bp.register_blueprint(maintenance_bp)
