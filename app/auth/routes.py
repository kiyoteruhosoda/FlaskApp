from flask import render_template, request, redirect, url_for, flash, session, current_app
import requests
import json
from datetime import datetime
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import gettext as _
from . import bp
from ..extensions import db
from ..models.user import User
from ..models.google_account import GoogleAccount
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
    # シークレットもテンプレートに渡す
    secret_display = secret
    if request.method == "POST":
        token = request.form.get("token")
        if not token or not verify_totp(secret, token):
            flash(_("Invalid authentication code"), "error")
            return render_template("auth/register_totp.html", qr_data=qr_data, secret=secret_display)
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
        login_user(u)
        return redirect(url_for("feature_x.dashboard"))
        #return redirect(url_for("auth.login"))
    return render_template("auth/register_totp.html", qr_data=qr_data, secret=secret_display)


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
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if not email:
            flash(_("Email is required"), "error")
            return render_template("auth/edit.html")
        if email != current_user.email and User.query.filter_by(email=email).first():
            flash(_("Email already exists"), "error")
            return render_template("auth/edit.html")
        current_user.email = email
        if password:
            current_user.set_password(password)
        db.session.commit()
        flash(_("Profile updated"), "success")
        return redirect(url_for("auth.edit"))
    return render_template("auth/edit.html")


@bp.route("/setup_totp", methods=["GET", "POST"])
@login_required
def setup_totp():
    if current_user.totp_secret:
        flash(_("Two-factor authentication already configured"), "error")
        return redirect(url_for("auth.edit"))
    secret = session.get("setup_totp_secret")
    if not secret:
        secret = new_totp_secret()
        session["setup_totp_secret"] = secret
    uri = provisioning_uri(current_user.email, secret)
    qr_data = qr_code_data_uri(uri)
    if request.method == "POST":
        token = request.form.get("token")
        if not token or not verify_totp(secret, token):
            flash(_("Invalid authentication code"), "error")
            return render_template("auth/setup_totp.html", qr_data=qr_data)
        current_user.totp_secret = secret
        db.session.commit()
        session.pop("setup_totp_secret", None)
        flash(_("Two-factor authentication enabled"), "success")
        return redirect(url_for("auth.edit"))
    return render_template("auth/setup_totp.html", qr_data=qr_data)

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash(_("Logged out"), "success")
    return redirect(url_for("index"))



@bp.get("/google/callback")
def google_oauth_callback():
    """Google OAuth callback handler."""
    if request.args.get("error"):
        flash(_("Google OAuth error: %(msg)s", msg=request.args["error"]), "error")
        return redirect(url_for("auth.google_accounts"))

    code = request.args.get("code")
    state = request.args.get("state")
    saved = session.get("google_oauth_state") or {}
    if not code or state != saved.get("state"):
        flash(_("Invalid OAuth state."), "error")
        return redirect(url_for("auth.google_accounts"))

    token_data = {
        "code": code,
        "client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
        "client_secret": current_app.config.get("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": url_for("auth.google_oauth_callback", _external=True),
        "grant_type": "authorization_code",
    }
    try:
        token_res = requests.post("https://oauth2.googleapis.com/token", data=token_data, timeout=10)
        tokens = token_res.json()
        if "error" in tokens:
            flash(_("Google token error: %(msg)s", msg=tokens.get("error_description", tokens["error"])), "error")
            return redirect(url_for("auth.google_accounts"))
    except Exception as e:
        flash(_("Failed to obtain token from Google: %(msg)s", msg=str(e)), "error")
        return redirect(url_for("auth.google_accounts"))

    access_token = tokens.get("access_token")
    email = None
    if access_token:
        try:
            ui_res = requests.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if ui_res.ok:
                email = ui_res.json().get("email")
        except Exception:
            email = None

    if not email:
        flash(_("Failed to fetch email from Google."), "error")
        return redirect(url_for("auth.google_accounts"))

    account = GoogleAccount.query.filter_by(email=email).first()
    scopes = saved.get("scopes") or []
    if not account:
        account = GoogleAccount(email=email, scopes=",".join(scopes))
        db.session.add(account)
    else:
        account.scopes = ",".join(scopes)
        account.status = "active"
    account.oauth_token_json = json.dumps(tokens)
    account.last_synced_at = datetime.utcnow()
    db.session.commit()

    redirect_to = saved.get("redirect") or url_for("auth.google_accounts")
    session.pop("google_oauth_state", None)
    flash(_("Google account linked: %(email)s", email=email), "success")
    return redirect(redirect_to)

@bp.route("/settings/google-accounts")
@login_required
def google_accounts():
    """Display Google account linkage settings."""
    accounts = GoogleAccount.query.all()
    return render_template("auth/google_accounts.html", accounts=accounts)