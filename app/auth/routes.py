from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import gettext as _
from . import bp
from ..extensions import db
from ..models.user import User

@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("feature_x.dashboard"))
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash(_("Invalid email or password"), "error")
            return render_template("auth/login.html")
        login_user(user)
        return redirect(url_for("feature_x.dashboard"))
    return render_template("auth/login.html")

@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role", "user")
        if not email or not password:
            flash(_("Email and password are required"), "error")
            return render_template("auth/register.html")
        if User.query.filter_by(email=email).first():
            flash(_("Email already exists"), "error")
            return render_template("auth/register.html")
        u = User(email=email, role=role)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        flash(_("Registration successful. Please log in."), "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html")

@bp.route("/edit", methods=["GET", "POST"])
@login_required
def edit():
    roles = ["user", "admin"]
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")
        if not email:
            flash(_("Email is required"), "error")
            return render_template("auth/edit.html", roles=roles)
        if email != current_user.email and User.query.filter_by(email=email).first():
            flash(_("Email already exists"), "error")
            return render_template("auth/edit.html", roles=roles)
        current_user.email = email
        if role:
            current_user.role = role
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
