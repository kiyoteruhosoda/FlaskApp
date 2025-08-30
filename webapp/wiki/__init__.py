"""
Wiki機能のFlask Blueprint
"""

from flask import Blueprint

bp = Blueprint("wiki", __name__, url_prefix="/wiki", template_folder="templates")

# Jinja2テンプレートフィルタを登録
from .utils import TEMPLATE_FILTERS
for filter_name, filter_func in TEMPLATE_FILTERS.items():
    bp.add_app_template_filter(filter_func, filter_name)

from . import routes  # noqa: F401
