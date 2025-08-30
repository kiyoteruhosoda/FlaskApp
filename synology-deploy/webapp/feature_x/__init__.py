from flask import Blueprint
bp = Blueprint("feature_x", __name__, template_folder="templates")
from . import routes  # noqa
