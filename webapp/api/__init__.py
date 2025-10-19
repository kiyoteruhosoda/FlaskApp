from flask_smorest import Blueprint

bp = Blueprint("api", __name__, description="Familink API")

from . import routes  # noqa: E402,F401
from . import health  # noqa: E402,F401
from . import picker_session  # noqa: E402,F401
from . import version  # noqa: E402,F401
from . import upload  # noqa: E402,F401
from . import maintenance  # noqa: E402,F401
from . import echo  # noqa: E402,F401
from . import service_account_keys  # noqa: E402,F401
from . import service_account_signing  # noqa: E402,F401

from .picker_session import bp as picker_session_bp

bp.register_blueprint(picker_session_bp)
