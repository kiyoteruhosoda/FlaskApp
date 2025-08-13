from flask import render_template
from flask_login import login_required
from flask_babel import gettext as _
from . import bp

@bp.route("/dashboard")
@login_required
def dashboard():
    # ここはログイン必須。未ログインなら auth.login へ自動リダイレクト
    return render_template("feature_x/dashboard.html")
