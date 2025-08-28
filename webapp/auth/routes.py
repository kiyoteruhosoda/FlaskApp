from flask import render_template, request, redirect, url_for, flash, session, current_app
import requests
import json
from datetime import datetime, timezone
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import gettext as _
from . import bp
from ..extensions import db
from core.models.user import User
from core.models.google_account import GoogleAccount
from core.crypto import encrypt, decrypt
from .totp import new_totp_secret, verify_totp, provisioning_uri, qr_code_data_uri
from core.models.picker_session import PickerSession
from .utils import refresh_google_token, log_requests_and_send, RefreshTokenError
from application.auth_service import AuthService
from infrastructure.user_repository import SqlAlchemyUserRepository


user_repo = SqlAlchemyUserRepository(db.session)
auth_service = AuthService(user_repo)

@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("feature_x.dashboard"))
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        token = request.form.get("token")
        user = auth_service.authenticate(email, password)
        if not user:
            flash(_("Invalid email or password"), "error")
            return render_template("auth/login.html")
        if user.totp_secret:
            if not token or not verify_totp(user.totp_secret, token):
                flash(_("Invalid authentication code"), "error")
                return render_template("auth/login.html")
        login_user(user_repo.get_model(user))
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
        if user_repo.get_by_email(email):
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
        try:
            u = auth_service.register(email, password, totp_secret=secret, roles=["member"])
        except ValueError:
            flash(_("Default role 'member' does not exist"), "error")
            return redirect(url_for("auth.register"))
        session.pop("reg_email", None)
        session.pop("reg_password", None)
        session.pop("reg_secret", None)
        flash(_("Registration successful"), "success")
        login_user(user_repo.get_model(u))
        return redirect(url_for("feature_x.dashboard"))
        #return redirect(url_for("auth.login"))
    return render_template("auth/register_totp.html", qr_data=qr_data, secret=secret_display)


@bp.route("/register/no_totp", methods=["GET", "POST"])
def register_no_totp():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if not email or not password:
            flash(_("Email and password are required"), "error")
            return render_template("auth/register_no_totp.html")
        if user_repo.get_by_email(email):
            flash(_("Email already exists"), "error")
            return render_template("auth/register_no_totp.html")
        try:
            auth_service.register(email, password, roles=["member"])
        except ValueError:
            flash(_("Default role 'member' does not exist"), "error")
            return render_template("auth/register_no_totp.html")
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
        token_res = log_requests_and_send(
            "post",
            "https://oauth2.googleapis.com/token",
            data=token_data,
            timeout=10
        )
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
            ui_res = log_requests_and_send(
                "get",
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
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
    account.oauth_token_json = encrypt(json.dumps(tokens))
    account.last_synced_at = datetime.now(timezone.utc)
    db.session.commit()

    redirect_to = saved.get("redirect") or url_for("auth.google_accounts")
    session.pop("google_oauth_state", None)
    flash(_("Google account linked: %(email)s", email=email), "success")
    return redirect(redirect_to)


@bp.get("/picker")
@login_required
def picker_auto():
    """Auto-select the first available Google account and create a Photo Picker session."""
    account = GoogleAccount.query.filter_by(user_id=current_user.id).first()
    if not account:
        flash(_("No Google account linked. Please link a Google account first."), "error")
        return redirect(url_for("auth.google_accounts"))
    return redirect(url_for("auth.picker", account_id=account.id))

@bp.get("/picker/<int:account_id>")
@login_required
def picker(account_id: int):
    """Create a Photo Picker session and show its URI as a QR code."""
    account = GoogleAccount.query.get_or_404(account_id)

    try:
        tokens = refresh_google_token(account)
    except RefreshTokenError as e:
        if str(e) == "no_refresh_token":
            flash(_("No refresh token available."), "error")
        else:
            flash(_("Failed to refresh token: %(msg)s", msg=str(e)), "error")
        return redirect(url_for("auth.google_accounts"))

    access_token = tokens.get("access_token")
    if not access_token:
        flash(_("Failed to obtain access token."), "error")
        return redirect(url_for("auth.google_accounts"))

    try:
        res = log_requests_and_send(
            "post",
            "https://photospicker.googleapis.com/v1/sessions",
            headers={"Authorization": f"Bearer {access_token}"},
            json_data={},
            timeout=10
        )
        res.raise_for_status()
        picker_data = res.json()
    except requests.RequestException as e:  # pragma: no cover - network failure
        flash(_("Failed to create picker session: %(msg)s", msg=str(e)), "error")
        return redirect(url_for("auth.google_accounts"))
    except ValueError:
        flash(_("Invalid response from picker API."), "error")
        return redirect(url_for("auth.google_accounts"))

    picker_uri = picker_data.get("pickerUri")
    if not picker_uri:
        msg = picker_data.get("error") or _("Failed to create picker session.")
        flash(msg, "error")
        return redirect(url_for("auth.google_accounts"))

    ps = PickerSession(
        account_id=account.id,
        session_id=picker_data.get("id"),
        picker_uri=picker_uri,
        status="pending",
    )
    expire = picker_data.get("expireTime")
    if expire:
        try:
            ps.expire_time = datetime.fromisoformat(expire.replace("Z", "+00:00"))
        except Exception:
            pass
    polling_conf = picker_data.get("pollingConfig") or {}
    if polling_conf:
        ps.polling_config_json = json.dumps(polling_conf)
    if picker_data.get("pickingConfig"):
        ps.picking_config_json = json.dumps(picker_data.get("pickingConfig"))
    if "mediaItemsSet" in picker_data:
        ps.media_items_set = picker_data.get("mediaItemsSet")
    db.session.add(ps)
    db.session.commit()

    poll_interval = polling_conf.get("pollInterval")
    qr_data = qr_code_data_uri(picker_uri)
    return render_template(
        "auth/picker.html",
        session_id=ps.session_id,
        picker_uri=picker_uri,
        qr_data=qr_data,
        poll_interval=poll_interval,
    )

@bp.route("/settings/google-accounts")
@login_required
def google_accounts():
    """Display Google account linkage settings."""
    accounts = GoogleAccount.query.filter_by(user_id=current_user.id).all()
    return render_template("auth/google_accounts.html", accounts=accounts)
