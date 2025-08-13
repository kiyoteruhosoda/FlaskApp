from flask import Blueprint, render_template
from flask_login import login_required, current_user
from flask_babel import gettext as _
from app.config import Config

from .routes import bp

@bp.route("/config")
@login_required
def show_config():
    if not current_user.can("system.settings"):
        return _(u"You do not have permission to access this page."), 403

    public_keys = [
        k for k in dir(Config)
        if not k.startswith("_") and k.isupper()
    ]
    config_dict = {k: getattr(Config, k) for k in public_keys}
    return render_template("admin/config_view.html", config=config_dict)
