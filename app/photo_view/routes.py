from flask import render_template
from flask_login import login_required
from flask_babel import gettext as _

from . import bp
from ..models.google_account import GoogleAccount


@bp.route("/settings/google-accounts")
@login_required
def google_accounts():
    """Display Google account linkage settings."""
    accounts = GoogleAccount.query.all()
    return render_template("photo_view/google_accounts.html", accounts=accounts)
