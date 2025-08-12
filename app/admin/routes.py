
from flask import Blueprint, render_template, flash, redirect, url_for, request
from ..extensions import db
from flask_login import login_required, current_user
from flask_babel import gettext as _
from ..models.user import User, Role

bp = Blueprint("admin", __name__, template_folder="templates")

# --- ここから各ルート定義 ---

# TOTPリセット
@bp.route("/users/<int:user_id>/reset_totp", methods=["POST"])
@login_required
def user_reset_totp(user_id):
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    user = User.query.get_or_404(user_id)
    # TOTPシークレットをリセット（Noneにする）
    user.totp_secret = None
    db.session.commit()
    flash(_("TOTP secret reset for user."), "success")
    return redirect(url_for("admin.users"))

# ユーザー削除
@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
def user_delete(user_id):
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash(_("You cannot delete yourself."), "error")
        return redirect(url_for("admin.users"))
    db.session.delete(user)
    db.session.commit()
    flash(_("User deleted successfully."), "success")
    return redirect(url_for("admin.users"))

# ユーザーロール変更
@bp.route("/users/<int:user_id>/role", methods=["POST"])
@login_required
def user_change_role(user_id):
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    user = User.query.get_or_404(user_id)
    role_id = request.form.get("role")
    role_obj = Role.query.get(int(role_id)) if role_id else None
    if not role_obj:
        flash(_("Selected role does not exist."), "error")
        return redirect(url_for("admin.users"))
    user.roles = [role_obj]
    db.session.commit()
    flash(_("User role updated."), "success")
    return redirect(url_for("admin.users"))

# ユーザー追加
@bp.route("/users/add", methods=["GET", "POST"])
@login_required
def user_add():
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    roles = Role.query.all()
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        role_id = request.form.get("role")
        if not email or not password or not role_id:
            flash(_("Email, password, and role are required."), "error")
            return render_template("admin/user_add.html", roles=roles)
        if User.query.filter_by(email=email).first():
            flash(_("Email already exists."), "error")
            return render_template("admin/user_add.html", roles=roles)
        role_obj = Role.query.get(int(role_id))
        if not role_obj:
            flash(_("Selected role does not exist."), "error")
            return render_template("admin/user_add.html", roles=roles)
        u = User(email=email)
        u.set_password(password)
        u.roles.append(role_obj)
        db.session.add(u)
        db.session.commit()
        flash(_("User created successfully."), "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/user_add.html", roles=roles)


@bp.route("/users", methods=["GET"])
@login_required
def users():
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    users = User.query.all()
    roles = Role.query.all()
    return render_template("admin/admin_users.html", users=users, roles=roles)
