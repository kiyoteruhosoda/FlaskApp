from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    current_app,
    make_response,
)
import requests
import json
from datetime import datetime, timezone, timedelta
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
from ..timezone import resolve_timezone, convert_to_timezone
from ..services.token_service import TokenService


user_repo = SqlAlchemyUserRepository(db.session)
auth_service = AuthService(user_repo)


PROFILE_TIMEZONES = [
    "UTC",
    "Asia/Tokyo",
    "Asia/Seoul",
    "Asia/Shanghai",
    "Asia/Singapore",
    "Australia/Sydney",
    "Europe/London",
    "Europe/Paris",
    "America/Los_Angeles",
    "America/New_York",
]

# セッション有効期限（30分）
SESSION_TIMEOUT_MINUTES = 30

def _is_session_expired(key_prefix):
    """セッションが期限切れかどうかをチェック"""
    timestamp_key = f"{key_prefix}_timestamp"
    timestamp = session.get(timestamp_key)
    if not timestamp:
        return True
    
    try:
        session_time = datetime.fromisoformat(timestamp)
        current_time = datetime.now(timezone.utc)
        return (current_time - session_time) > timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    except (ValueError, TypeError):
        return True

def _set_session_timestamp(key_prefix):
    """セッションのタイムスタンプを設定"""
    timestamp_key = f"{key_prefix}_timestamp"
    session[timestamp_key] = datetime.now(timezone.utc).isoformat()

def _clear_registration_session():
    """登録関連のセッションデータをクリア"""
    keys_to_clear = ["reg_user_id", "reg_secret", "reg_timestamp"]
    for key in keys_to_clear:
        session.pop(key, None)

def _clear_setup_totp_session():
    """2FA設定関連のセッションデータをクリア"""
    keys_to_clear = ["setup_totp_secret", "setup_totp_timestamp"]
    for key in keys_to_clear:
        session.pop(key, None)


def _complete_registration(user):
    """ユーザー登録完了後の共通処理"""
    flash(_("Registration successful"), "success")
    login_user(user_repo.get_model(user))
    return redirect(url_for("feature_x.dashboard"))


def _validate_registration_input(email, password, template_name):
    """登録時の入力バリデーション"""
    if not email or not password:
        flash(_("Email and password are required"), "error")
        return render_template(template_name)
    if user_repo.get_by_email(email):
        flash(_("Email already exists"), "error")
        return render_template(template_name)
    return None


def _handle_registration_error(template_name, **template_kwargs):
    """登録時のロールエラーハンドリング"""
    flash(_("Default role 'guest' does not exist"), "error")
    if template_name == "auth/register_totp.html":
        return redirect(url_for("auth.register"))
    return render_template(template_name, **template_kwargs)


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
        
        # アクティブユーザーが存在するかチェック
        existing_user = user_repo.get_by_email(email)
        if existing_user and existing_user.is_active:
            flash(_("Email already exists"), "error")
            return render_template("auth/register.html")
        
        # 既存の登録セッションをクリア
        _clear_registration_session()
        
        try:
            # TOTP設定待ちの非アクティブユーザーとして登録
            u = auth_service.register_with_pending_totp(email, password, roles=["guest"])
            
            secret = new_totp_secret()
            session["reg_user_id"] = u.id
            session["reg_secret"] = secret
            _set_session_timestamp("reg")
            return redirect(url_for("auth.register_totp"))
        except ValueError as e:
            flash(_("Registration failed: {}").format(str(e)), "error")
            return render_template("auth/register.html")
    return render_template("auth/register.html")


@bp.route("/register/totp", methods=["GET", "POST"])
def register_totp():
    user_id = session.get("reg_user_id")
    secret = session.get("reg_secret")
    
    # セッション有効性をチェック
    if not user_id or not secret or _is_session_expired("reg"):
        _clear_registration_session()
        flash(_("Session expired. Please register again."), "error")
        return redirect(url_for("auth.register"))
    
    # ユーザーを取得
    user_model = User.query.get(user_id)
    if not user_model or user_model.is_active:
        _clear_registration_session()
        flash(_("Registration session invalid. Please register again."), "error")
        return redirect(url_for("auth.register"))
    
    uri = provisioning_uri(user_model.email, secret)
    qr_data = qr_code_data_uri(uri)
    
    if request.method == "POST":
        token = request.form.get("token")
        if not token or not verify_totp(secret, token):
            flash(_("Invalid authentication code"), "error")
            return render_template("auth/register_totp.html", qr_data=qr_data, secret=secret)
        
        try:
            # ユーザーをTOTPと共にアクティブ化
            domain_user = user_repo._to_domain(user_model)
            u = auth_service.activate_user_with_totp(domain_user, secret)
            
            _clear_registration_session()
            flash(_("Registration successful"), "success")
            login_user(user_repo.get_model(u))
            return redirect(url_for("feature_x.dashboard"))
        except Exception as e:
            flash(_("Registration failed: {}").format(str(e)), "error")
            return render_template("auth/register_totp.html", qr_data=qr_data, secret=secret)
    
    return render_template("auth/register_totp.html", qr_data=qr_data, secret=secret)


@bp.route("/register/totp/cancel", methods=["POST"])
def register_totp_cancel():
    """2FA登録をキャンセルして、非アクティブユーザーを削除"""
    user_id = session.get("reg_user_id")
    
    if user_id:
        # 非アクティブユーザーを削除
        user_model = User.query.get(user_id)
        if user_model and not user_model.is_active:
            domain_user = user_repo._to_domain(user_model)
            user_repo.delete(domain_user)
    
    _clear_registration_session()
    flash(_("Registration cancelled. You can start over."), "info")
    return redirect(url_for("auth.register"))


@bp.route("/register/no_totp", methods=["GET", "POST"])
def register_no_totp():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        
        # 入力バリデーション
        validation_error = _validate_registration_input(email, password, "auth/register_no_totp.html")
        if validation_error:
            return validation_error
        
        try:
            u = auth_service.register(email, password, roles=["guest"])
        except ValueError:
            return _handle_registration_error("auth/register_no_totp.html")
        
        return _complete_registration(u)
    
    return render_template("auth/register_no_totp.html")


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    languages = current_app.config.get("LANGUAGES", ["ja", "en"])
    if not languages:
        languages = [current_app.config.get("BABEL_DEFAULT_LOCALE", "en")]
    language_labels = {
        "ja": _("Japanese"),
        "en": _("English"),
    }
    default_language = current_app.config.get("BABEL_DEFAULT_LOCALE", languages[0])
    if default_language not in language_labels:
        language_labels[default_language] = default_language
    selected_language = request.cookies.get("lang") or default_language
    if selected_language not in languages:
        selected_language = default_language

    default_timezone = current_app.config.get("BABEL_DEFAULT_TIMEZONE", "UTC")
    timezone_codes = list(PROFILE_TIMEZONES)
    if default_timezone not in timezone_codes:
        timezone_codes.insert(0, default_timezone)

    selected_timezone = request.cookies.get("tz") or default_timezone
    if selected_timezone not in timezone_codes:
        selected_timezone = (
            default_timezone if default_timezone in timezone_codes else timezone_codes[0]
        )

    selected_timezone, tzinfo = resolve_timezone(selected_timezone, default_timezone)
    server_time_utc = datetime.now(timezone.utc)
    localized_time = convert_to_timezone(server_time_utc, tzinfo)

    if request.method == "POST":
        form_lang = request.form.get("language")
        form_tz = request.form.get("timezone")
        response = make_response(redirect(url_for("auth.profile")))
        updated = False

        if form_lang and form_lang in languages:
            selected_language = form_lang
            response.set_cookie(
                "lang",
                form_lang,
                max_age=60 * 60 * 24 * 30,
                httponly=False,
                samesite="Lax",
            )
            updated = True

        if form_tz and form_tz in timezone_codes:
            selected_timezone, tzinfo = resolve_timezone(form_tz, default_timezone)
            localized_time = convert_to_timezone(server_time_utc, tzinfo)
            response.set_cookie(
                "tz",
                selected_timezone,
                max_age=60 * 60 * 24 * 30,
                httponly=False,
                samesite="Lax",
            )
            updated = True

        if updated:
            flash(_("Profile preferences updated."), "success")
        else:
            flash(_("No changes were applied."), "info")
        return response

    language_choices = [
        {"code": code, "label": language_labels.get(code, code)} for code in languages
    ]
    timezone_labels = {
        "UTC": _("UTC"),
        "Asia/Tokyo": _("Asia/Tokyo (Japan)"),
        "Asia/Seoul": _("Asia/Seoul (Korea)"),
        "Asia/Shanghai": _("Asia/Shanghai (China)"),
        "Asia/Singapore": _("Asia/Singapore"),
        "Australia/Sydney": _("Australia/Sydney"),
        "Europe/London": _("Europe/London (UK)"),
        "Europe/Paris": _("Europe/Paris (France)"),
        "America/Los_Angeles": _("America/Los Angeles (USA)"),
        "America/New_York": _("America/New York (USA)"),
    }
    if default_timezone not in timezone_labels:
        timezone_labels[default_timezone] = default_timezone
    timezone_choices = []
    for code in timezone_codes:
        label = timezone_labels.get(code)
        if not label:
            label = code
        timezone_choices.append({"code": code, "label": label})

    return render_template(
        "auth/profile.html",
        language_choices=language_choices,
        selected_language=selected_language,
        timezone_choices=timezone_choices,
        selected_timezone=selected_timezone,
        server_time_utc=server_time_utc,
        localized_time=localized_time,
    )


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
        return redirect(url_for("auth.profile"))
    return render_template("auth/edit.html")


@bp.route("/setup_totp", methods=["GET", "POST"])
@login_required
def setup_totp():
    if current_user.totp_secret:
        flash(_("Two-factor authentication already configured"), "error")
        return redirect(url_for("auth.edit"))
    
    secret = session.get("setup_totp_secret")
    
    # セッション有効性をチェック
    if secret and _is_session_expired("setup_totp"):
        _clear_setup_totp_session()
        secret = None
    
    if not secret:
        secret = new_totp_secret()
        session["setup_totp_secret"] = secret
        _set_session_timestamp("setup_totp")
    
    uri = provisioning_uri(current_user.email, secret)
    qr_data = qr_code_data_uri(uri)
    
    if request.method == "POST":
        token = request.form.get("token")
        if not token or not verify_totp(secret, token):
            flash(_("Invalid authentication code"), "error")
            return render_template("auth/setup_totp.html", qr_data=qr_data, secret=secret)
        current_user.totp_secret = secret
        db.session.commit()
        _clear_setup_totp_session()
        flash(_("Two-factor authentication enabled"), "success")
        return redirect(url_for("auth.edit"))
    return render_template("auth/setup_totp.html", qr_data=qr_data, secret=secret)

@bp.route("/setup_totp/cancel", methods=["POST"])
@login_required
def setup_totp_cancel():
    """2FA設定をキャンセル"""
    _clear_setup_totp_session()
    flash(_("Two-factor authentication setup cancelled."), "info")
    return redirect(url_for("auth.edit"))

@bp.route("/logout")
@login_required
def logout():
    user = current_user._get_current_object()
    user_payload = {
        "message": "User logged out",
        "user_id": user.id,
        "email": user.email,
    }

    TokenService.revoke_refresh_token(user)
    logout_user()
    session.pop("picker_session_id", None)

    response = make_response(redirect(url_for("index")))
    response.delete_cookie("access_token")

    current_app.logger.info(
        json.dumps(user_payload, ensure_ascii=False),
        extra={"event": "auth.logout", "path": request.path},
    )

    flash(_("Logged out"), "success")
    return response



@bp.get("/google/callback")
def google_oauth_callback():
    """Google OAuth callback handler."""
    if request.args.get("error"):
        flash(_("Google OAuth error: %(msg)s", msg=request.args["error"]), "error")
        return redirect(url_for("admin.google_accounts"))

    code = request.args.get("code")
    state = request.args.get("state")
    saved = session.get("google_oauth_state") or {}
    if not code or state != saved.get("state"):
        flash(_("Invalid OAuth state."), "error")
        return redirect(url_for("admin.google_accounts"))

    token_data = {
        "code": code,
        "client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
        "client_secret": current_app.config.get("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": url_for("auth.google_oauth_callback", _external=True),
        "grant_type": "authorization_code",
    }

    # デバッグログを追加
    current_app.logger.info(f"OAuth callback - client_id: {token_data['client_id']}")
    current_app.logger.info(f"OAuth callback - client_secret exists: {bool(token_data['client_secret'])}")
    current_app.logger.info(f"OAuth callback - redirect_uri: {token_data['redirect_uri']}")

    try:
        token_res = log_requests_and_send(
            "post",
            "https://oauth2.googleapis.com/token",
            data=token_data,
            timeout=10
        )
        tokens = token_res.json()
        current_app.logger.info(f"OAuth token response: {tokens}")
        if "error" in tokens:
            flash(_("Google token error: %(msg)s", msg=tokens.get("error_description", tokens["error"])), "error")
            return redirect(url_for("admin.google_accounts"))
    except Exception as e:
        current_app.logger.error(f"Failed to obtain token from Google: {str(e)}")
        flash(_("Failed to obtain token from Google: %(msg)s", msg=str(e)), "error")
        return redirect(url_for("admin.google_accounts"))

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
        return redirect(url_for("admin.google_accounts"))

    account = GoogleAccount.query.filter_by(email=email).first()
    scopes = saved.get("scopes") or []
    if not account:
        account = GoogleAccount(email=email, scopes=",".join(scopes), user_id=current_user.id)
        db.session.add(account)
    else:
        account.scopes = ",".join(scopes)
        account.status = "active"
        account.user_id = current_user.id
    account.oauth_token_json = encrypt(json.dumps(tokens))
    account.last_synced_at = datetime.now(timezone.utc)
    db.session.commit()

    redirect_to = saved.get("redirect") or url_for("admin.google_accounts")
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
        return redirect(url_for("admin.google_accounts"))
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
        return redirect(url_for("admin.google_accounts"))

    access_token = tokens.get("access_token")
    if not access_token:
        flash(_("Failed to obtain access token."), "error")
        return redirect(url_for("admin.google_accounts"))

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
        return redirect(url_for("admin.google_accounts"))
    except ValueError:
        flash(_("Invalid response from picker API."), "error")
        return redirect(url_for("admin.google_accounts"))

    picker_uri = picker_data.get("pickerUri")
    if not picker_uri:
        msg = picker_data.get("error") or _("Failed to create picker session.")
        flash(msg, "error")
        return redirect(url_for("admin.google_accounts"))

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
    """Redirect to admin Google accounts page."""
    return redirect(url_for("admin.google_accounts"))
