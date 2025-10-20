from flask import Flask
import pytest

from flask import Flask
import pytest

from webapp.api.blueprint import AuthEnforcedBlueprint
from webapp.api.health import skip_auth
from webapp.api.routes import login_or_jwt_required
from webapp.auth.service_account_auth import require_service_account_scopes


def _register_routes(blueprint):
    app = Flask(__name__)
    app.register_blueprint(blueprint)


def test_route_registration_requires_auth_decorator():
    bp = AuthEnforcedBlueprint("test", __name__)

    with pytest.raises(RuntimeError):

        @bp.get("/forbidden")
        def forbidden_route():
            return "nope"


def test_route_registration_allows_skip_auth():
    bp = AuthEnforcedBlueprint("test", __name__)

    @bp.get("/health")
    @skip_auth
    def health_route():
        return "ok"

    _register_routes(bp)


def test_route_registration_allows_login_or_jwt_required():
    bp = AuthEnforcedBlueprint("test", __name__)

    @bp.get("/secure")
    @login_or_jwt_required
    def secure_route():
        return "ok"

    _register_routes(bp)


def test_route_registration_allows_service_account_auth():
    bp = AuthEnforcedBlueprint("test", __name__)

    @bp.get("/maintenance")
    @require_service_account_scopes(["maintenance:read"], audience=lambda _: "test")
    def maintenance_route():
        return "ok"

    _register_routes(bp)
