from flask import render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import gettext as _
from . import bp
from ..extensions import db
from ..models.user import User
from .totp import new_totp_secret, verify_totp, provisioning_uri, qr_code_data_uri

@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("feature_x.dashboard"))
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        token = request.form.get("token")
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash(_("Invalid email or password"), "error")
            return render_template("auth/login.html")
        if user.totp_secret:
            if not token or not verify_totp(user.totp_secret, token):
                flash(_("Invalid authentication code"), "error")
                return render_template("auth/login.html")
        login_user(user)
        return redirect(url_for("feature_x.dashboard"))
    return render_template("auth/login.html")

@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if not email or not password:
            flash(_("Email and password are required"), "error")
            return render_template("auth/register.html")
        if User.query.filter_by(email=email).first():
            flash(_("Email already exists"), "error")
            return render_template("auth/register.html")
        secret = new_totp_secret()
        session["reg_email"] = email
        session["reg_password"] = password
        session["reg_secret"] = secret
        return redirect(url_for("auth.register_totp"))
    return render_template("auth/register.html")


@bp.route("/register/totp", methods=["GET", "POST"])
def register_totp():
    from ..models.user import Role
    email = session.get("reg_email")
    password = session.get("reg_password")
    secret = session.get("reg_secret")
    if not email or not password or not secret:
        flash(_("Session expired. Please register again."), "error")
        return redirect(url_for("auth.register"))
    uri = provisioning_uri(email, secret)
    qr_data = qr_code_data_uri(uri)
    if request.method == "POST":
        token = request.form.get("token")
        if not token or not verify_totp(secret, token):
            flash(_("Invalid authentication code"), "error")
            return render_template("auth/register_totp.html", qr_data=qr_data)
        u = User(email=email)
        u.set_password(password)
        u.totp_secret = secret
        member_role = Role.query.filter_by(name='member').first()
        if not member_role:
            flash(_("Default role 'member' does not exist"), "error")
            return redirect(url_for("auth.register"))
        u.roles.append(member_role)
        db.session.add(u)
        db.session.commit()
        session.pop("reg_email", None)
        session.pop("reg_password", None)
        session.pop("reg_secret", None)
        flash(_("Registration successful"), "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register_totp.html", qr_data=qr_data)


@bp.route("/register/no_totp", methods=["GET", "POST"])
def register_no_totp():
    from ..models.user import Role
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if not email or not password:
            flash(_("Email and password are required"), "error")
            return render_template("auth/register_no_totp.html")
        if User.query.filter_by(email=email).first():
            flash(_("Email already exists"), "error")
            return render_template("auth/register_no_totp.html")
        u = User(email=email)
        u.set_password(password)
        member_role = Role.query.filter_by(name='member').first()
        if not member_role:
            flash(_("Default role 'member' does not exist"), "error")
            return render_template("auth/register_no_totp.html")
        u.roles.append(member_role)
        db.session.add(u)
        db.session.commit()
        flash(_("Registration successful"), "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register_no_totp.html")

@bp.route("/edit", methods=["GET", "POST"])
@login_required
def edit():
    from ..models.user import Role
    roles = Role.query.all()
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        role_id = request.form.get("role")
        if not email:
            flash(_("Email is required"), "error")
            return render_template("auth/edit.html", roles=roles)
        if email != current_user.email and User.query.filter_by(email=email).first():
            flash(_("Email already exists"), "error")
            return render_template("auth/edit.html", roles=roles)
        current_user.email = email
        if role_id:
            from ..models.user import Role
            role_obj = Role.query.get(int(role_id))
            if role_obj and role_obj not in current_user.roles:
                current_user.roles = [role_obj]
        if password:
            current_user.set_password(password)
        db.session.commit()
        flash(_("Profile updated"), "success")
        return redirect(url_for("feature_x.dashboard"))
    return render_template("auth/edit.html", roles=roles)

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash(_("Logged out"), "success")
    return redirect(url_for("index"))
