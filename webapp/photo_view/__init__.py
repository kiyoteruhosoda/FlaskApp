from flask import Blueprint

bp = Blueprint("photo_view", __name__, template_folder="templates")

from . import routes  # noqa: F401
