from .blueprint import AuthEnforcedBlueprint

bp = AuthEnforcedBlueprint("api", __name__, description="nolumia API")

from . import routes  # noqa: E402,F401
from . import routes_local_import  # noqa: E402,F401
from . import routes_totp  # noqa: E402,F401
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
