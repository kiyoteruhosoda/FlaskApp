from shared.infrastructure.models.authz import require_perms
from presentation.web.routes.react_routes import serve_react_app
from . import bp


@bp.route("/")
@require_perms("dashboard:view")
def dashboard():
    """Serve the React dashboard shell.

    This endpoint exists primarily as a ``url_for("dashboard.dashboard")``
    target.  It serves the SPA directly rather than redirecting to
    ``/dashboard`` which – due to the trailing-slash canonicalisation of this
    blueprint route – would bounce between ``/dashboard`` and ``/dashboard/``.
    """
    return serve_react_app('dashboard')
