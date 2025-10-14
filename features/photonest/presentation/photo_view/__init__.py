from flask import Blueprint

bp = Blueprint(
    "photo_view",
    __name__,
    url_prefix="/photo_view",
    template_folder="templates",
)

from . import routes  # noqa: F401
