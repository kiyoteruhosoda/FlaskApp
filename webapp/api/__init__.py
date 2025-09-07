from flask import Blueprint

bp = Blueprint("api", __name__, template_folder="templates")

from . import routes  # noqa
from . import health  # noqa
from . import picker_session  # noqa
from . import openapi  # noqa
from . import version  # noqa

# picker_session Blueprintをapi Blueprintに登録
from .picker_session import bp as picker_session_bp
bp.register_blueprint(picker_session_bp)
