from flask import redirect
from core.models.authz import require_perms
from . import bp


@bp.route("/")
@require_perms("dashboard:view")
def dashboard():
    """Redirect to the React dashboard."""
    return redirect("/dashboard")
