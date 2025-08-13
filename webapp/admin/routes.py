
from flask import Blueprint, render_template, flash, redirect, url_for, request
from ..extensions import db
from flask_login import login_required, current_user
from flask_babel import gettext as _

from core.models.user import User, Role, Permission


bp = Blueprint("admin", __name__, template_folder="templates")


# --- ここから各ルート定義 ---


# Config表示ページ（管理者のみ）
@bp.route("/config")
@login_required
def show_config():
    if not (hasattr(current_user, 'has_role') and current_user.has_role("admin")):
        return _(u"You do not have permission to access this page."), 403
    # Only show public config values, not secrets
    from webapp.config import Config
    public_keys = [
        k for k in dir(Config)
        if not k.startswith("_") and k.isupper() and k not in ("SECRET_KEY")
    ]
    config_dict = {k: getattr(Config, k) for k in public_keys}
    return render_template("admin/config_view.html", config=config_dict)

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


@bp.route("/permissions", methods=["GET"])
@login_required
def permissions():
    if not current_user.can('permission:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    search = request.args.get("search", "").strip()
    sort = request.args.get("sort", "id")
    order = request.args.get("order", "asc")

    query = Permission.query
    if search:
        query = query.filter(Permission.code.contains(search))

    if sort not in ["id", "code"]:
        sort = "id"
    sort_column = getattr(Permission, sort)
    if order == "desc":
        sort_column = sort_column.desc()
    else:
        sort_column = sort_column.asc()

    perms = query.order_by(sort_column).all()
    return render_template(
        "admin/permissions.html", permissions=perms, search=search, sort=sort, order=order
    )


@bp.route("/permissions/add", methods=["GET", "POST"])
@login_required
def permission_add():
    if not current_user.can('permission:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    if request.method == "POST":
        code = request.form.get("code")
        if not code:
            flash(_("Code is required."), "error")
            return render_template("admin/permission_edit.html", permission=None)
        if Permission.query.filter_by(code=code).first():
            flash(_("Permission already exists."), "error")
            return render_template("admin/permission_edit.html", permission=None)
        p = Permission(code=code)
        db.session.add(p)
        db.session.commit()
        flash(_("Permission created successfully."), "success")
        return redirect(url_for("admin.permissions"))
    return render_template("admin/permission_edit.html", permission=None)


@bp.route("/permissions/<int:perm_id>/edit", methods=["GET", "POST"])
@login_required
def permission_edit(perm_id):
    if not current_user.can('permission:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    perm = Permission.query.get_or_404(perm_id)
    if request.method == "POST":
        code = request.form.get("code")
        if not code:
            flash(_("Code is required."), "error")
            return render_template("admin/permission_edit.html", permission=perm)
        perm.code = code
        db.session.commit()
        flash(_("Permission updated."), "success")
        return redirect(url_for("admin.permissions"))
    return render_template("admin/permission_edit.html", permission=perm)


@bp.route("/permissions/<int:perm_id>/delete", methods=["POST"])
@login_required
def permission_delete(perm_id):
    if not current_user.can('permission:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    perm = Permission.query.get_or_404(perm_id)
    db.session.delete(perm)
    db.session.commit()
    flash(_("Permission deleted."), "success")
    return redirect(url_for("admin.permissions"))


@bp.route("/roles", methods=["GET"])
@login_required
def roles():
    if not current_user.can('role:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    roles = Role.query.all()
    return render_template("admin/roles.html", roles=roles)


@bp.route("/roles/add", methods=["GET", "POST"])
@login_required
def role_add():
    if not current_user.can('role:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    permissions = Permission.query.all()
    if request.method == "POST":
        name = request.form.get("name")
        perm_ids = request.form.getlist("permissions")
        if not name:
            flash(_("Name is required."), "error")
            return render_template("admin/role_edit.html", role=None, permissions=permissions, selected=[])
        if Role.query.filter_by(name=name).first():
            flash(_("Role already exists."), "error")
            return render_template("admin/role_edit.html", role=None, permissions=permissions, selected=[])
        role = Role(name=name)
        for pid in perm_ids:
            perm = Permission.query.get(int(pid))
            if perm:
                role.permissions.append(perm)
        db.session.add(role)
        db.session.commit()
        flash(_("Role created successfully."), "success")
        return redirect(url_for("admin.roles"))
    return render_template("admin/role_edit.html", role=None, permissions=permissions, selected=[])


@bp.route("/roles/<int:role_id>/edit", methods=["GET", "POST"])
@login_required
def role_edit(role_id):
    if not current_user.can('role:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    role = Role.query.get_or_404(role_id)
    permissions = Permission.query.all()
    if request.method == "POST":
        name = request.form.get("name")
        perm_ids = request.form.getlist("permissions")
        if not name:
            flash(_("Name is required."), "error")
            return render_template("admin/role_edit.html", role=role, permissions=permissions, selected=[p.id for p in role.permissions])
        role.name = name
        role.permissions = []
        for pid in perm_ids:
            perm = Permission.query.get(int(pid))
            if perm:
                role.permissions.append(perm)
        db.session.commit()
        flash(_("Role updated."), "success")
        return redirect(url_for("admin.roles"))
    selected = [p.id for p in role.permissions]
    return render_template("admin/role_edit.html", role=role, permissions=permissions, selected=selected)


@bp.route("/roles/<int:role_id>/delete", methods=["POST"])
@login_required
def role_delete(role_id):
    if not current_user.can('role:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    role = Role.query.get_or_404(role_id)
    db.session.delete(role)
    db.session.commit()
    flash(_("Role deleted."), "success")
    return redirect(url_for("admin.roles"))
