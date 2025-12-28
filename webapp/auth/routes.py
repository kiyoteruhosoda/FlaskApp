from flask import (
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    current_app,
    make_response,
    g,
    jsonify,
)
import requests
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable
from urllib.parse import urlsplit
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import gettext as _, force_locale
from sqlalchemy import select
from . import (
    SERVICE_LOGIN_SESSION_KEY,
    SERVICE_LOGIN_TOKEN_SESSION_KEY,
    bp,
)
from ..extensions import db
from core.models.user import User
from core.models.google_account import GoogleAccount
from core.crypto import encrypt, decrypt
from .totp import new_totp_secret, verify_totp, provisioning_uri, qr_code_data_uri
from core.models.picker_session import PickerSession
from .utils import refresh_google_token, log_requests_and_send, RefreshTokenError
from shared.application.auth_service import AuthService
from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.application.passkey_service import (
    PasskeyAuthenticationError,
    PasskeyRegistrationError,
    PasskeyService,
)
from shared.domain.user import UserRegistrationService
from shared.infrastructure.passkey_repository import SqlAlchemyPasskeyRepository
from shared.infrastructure.user_repository import SqlAlchemyUserRepository
from ..timezone import resolve_timezone, convert_to_timezone
from ..services.token_service import TokenService
from ..services.gui_access_cookie import (
    API_LOGIN_SCOPE_SESSION_KEY,
    apply_gui_access_cookie,
    normalize_scope_items,
)
from core.settings import settings
from ..utils import determine_external_scheme
from webauthn.helpers import base64url_to_bytes


user_repo = SqlAlchemyUserRepository(db.session)
user_registration_service = UserRegistrationService(user_repo)
auth_service = AuthService(user_repo, user_registration_service)
passkey_repo = SqlAlchemyPasskeyRepository(db.session)
passkey_service = PasskeyService(passkey_repo)


PROFILE_TIMEZONES = [
    "UTC",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Singapore",
    "Australia/Sydney",
    "Europe/London",
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
]

# セッション有効期限（30分）
SESSION_TIMEOUT_MINUTES = 30

PASSKEY_REGISTRATION_CHALLENGE_KEY = "passkey_registration_challenge"
PASSKEY_REGISTRATION_USER_ID_KEY = "passkey_registration_user_id"
PASSKEY_AUTH_CHALLENGE_KEY = "passkey_authentication_challenge"


def _extract_passkey_credential_payload(
    payload: Any,
    *,
    meta_keys: Iterable[str] | None = None,
    required_keys: Iterable[str] | None = None,
) -> dict | None:
    """Return a credential payload extracted from *payload* when possible."""

    if not isinstance(payload, dict):
        return None

    nested = payload.get("credential")
    required = set(required_keys or ())
    if isinstance(nested, dict):
        if required and not required.issubset(nested):
            return None
        return nested

    meta = set(meta_keys or ())
    candidate = {key: value for key, value in payload.items() if key not in meta}
    if not candidate:
        return None

    if required and not required.issubset(candidate):
        return None

    return candidate


def _gather_passkey_payload_keys(
    payload: Any,
    *,
    meta_keys: Iterable[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Return lists of root, credential, and response keys for logging."""

    if not isinstance(payload, dict):
        return [], [], []

    root_keys = sorted(payload.keys())
    nested = payload.get("credential")
    meta = set(meta_keys or ())

    if isinstance(nested, dict):
        credential_payload: Any = nested
    else:
        credential_payload = {key: value for key, value in payload.items() if key not in meta}

    credential_keys: list[str] = []
    response_keys: list[str] = []

    if isinstance(credential_payload, dict):
        credential_keys = sorted(credential_payload.keys())
        response = credential_payload.get("response")
        if isinstance(response, dict):
            response_keys = sorted(response.keys())

    return root_keys, credential_keys, response_keys


def _extract_passkey_client_data_details(
    credential_payload: dict[str, Any],
) -> dict[str, Any]:
    """Decode clientDataJSON and return challenge/origin details."""

    details: dict[str, Any] = {
        "challenge": None,
        "origin": None,
        "raw": None,
        "error": None,
    }

    response_section = credential_payload.get("response")
    if not isinstance(response_section, dict):
        return details

    encoded_client_data = response_section.get("clientDataJSON")
    if not isinstance(encoded_client_data, str):
        return details

    try:
        decoded_bytes = base64url_to_bytes(encoded_client_data)
    except Exception as exc:
        details["error"] = f"decode_error: {exc}"
        return details

    try:
        decoded_text = decoded_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        details["error"] = f"utf8_error: {exc}"
        return details

    details["raw"] = decoded_text

    try:
        parsed = json.loads(decoded_text)
    except Exception as exc:
        details["error"] = f"json_error: {exc}"
        return details

    if isinstance(parsed, dict):
        details["challenge"] = parsed.get("challenge")
        details["origin"] = parsed.get("origin")

    return details


def _format_exception_chain(exc: Exception) -> str | None:
    """Return a compact string summarizing the exception cause chain."""

    chain: list[str] = []
    current: Exception | None = exc.__cause__ if exc.__cause__ is not None else exc.__context__

    while current is not None:
        chain.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ if current.__cause__ is not None else current.__context__

    if not chain:
        return None

    return " | ".join(chain)


def _build_passkey_trace_payload(
    *,
    cause: str | None,
    expected_challenge: str | None,
    client_data_details: dict[str, Any],
    expected_rp_id: str | None,
    expected_origin: str | None,
) -> str | None:
    """Serialize trace details for structured logging."""

    raw_client_data = client_data_details.get("raw")
    preview = None
    if isinstance(raw_client_data, str):
        max_length = 512
        preview = raw_client_data if len(raw_client_data) <= max_length else f"{raw_client_data[:max_length]}…"

    payload = {
        "cause": cause,
        "expected_challenge": expected_challenge,
        "client_challenge": client_data_details.get("challenge"),
        "expected_rp_id": expected_rp_id,
        "expected_origin": expected_origin,
        "client_origin": client_data_details.get("origin"),
        "client_data_error": client_data_details.get("error"),
        "client_data_json_preview": preview,
    }

    sanitized = {key: value for key, value in payload.items() if value is not None}
    if not sanitized:
        return None

    return json.dumps(sanitized, ensure_ascii=False)


_DEFAULT_RP_ID_SENTINELS = {"localhost", "127.0.0.1"}
_DEFAULT_ORIGIN_SENTINELS = {
    "http://localhost",
    "http://localhost:5000",
    "https://localhost",
    "https://localhost:5000",
}


def _resolve_passkey_rp_id() -> str:
    """Determine the relying party ID for the current request."""

    candidate = settings.webauthn_rp_id
    host = request.host.split(":", 1)[0] if request.host else None

    if not host:
        return candidate

    if candidate in _DEFAULT_RP_ID_SENTINELS and host not in _DEFAULT_RP_ID_SENTINELS:
        return host

    return candidate


def _resolve_passkey_origin() -> str:
    """Determine the expected origin for WebAuthn operations."""

    candidate = settings.webauthn_origin.rstrip("/")
    host = request.host
    if not host:
        return candidate

    derived_scheme = determine_external_scheme(request)
    derived = f"{derived_scheme}://{host}".rstrip("/")

    if candidate.rstrip("/") in _DEFAULT_ORIGIN_SENTINELS and derived not in _DEFAULT_ORIGIN_SENTINELS:
        return derived

    return candidate


def _normalize_redirect_target(location: str | None, *, fallback: str = "/") -> str:
    """Normalize redirect targets to avoid malformed ``Location`` headers."""

    if not location:
        return fallback

    value = location.strip()
    if not value:
        return fallback

    lowered = value.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return value

    parsed = None
    if value.startswith("//"):
        parsed = urlsplit(value)
        path = parsed.path or ""
    elif value.startswith("://"):
        parsed = urlsplit(f"http{value}")
        path = parsed.path or ""
    elif "://" in value:
        parsed = urlsplit(value)
        if parsed.scheme and parsed.netloc:
            return value
        path = parsed.path or ""
    else:
        path = value

    if not path:
        path = fallback

    if not path.startswith("/"):
        path = f"/{path}"

    query = parsed.query if parsed is not None else ""
    fragment = parsed.fragment if parsed is not None else ""

    if not query and not fragment:
        return path

    result = path
    if query:
        result = f"{result}?{query}"
    if fragment:
        result = f"{result}#{fragment}"
    return result


def _relative_url_for(endpoint: str, **values) -> str:
    return _normalize_redirect_target(url_for(endpoint, **values))


def _redirect_to(endpoint: str, **values):
    return redirect(_relative_url_for(endpoint, **values))


def _sync_active_role(user_model):
    """Ensure the active role stored in the session is valid for the given user."""
    role_ids = [role.id for role in getattr(user_model, "roles", [])]
    if not role_ids:
        session.pop("active_role_id", None)
        return

    active_role_id = session.get("active_role_id")
    if active_role_id in role_ids:
        return

    if len(role_ids) == 1:
        session["active_role_id"] = role_ids[0]
    else:
        session["active_role_id"] = role_ids[0]
    
    session.modified = True


def _resolve_post_login_target() -> str:
    """決定したリダイレクト先を返す。安全なパスに限定する。"""
    candidate = request.form.get("next") or request.args.get("next")
    if candidate and candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return _relative_url_for("dashboard.dashboard")


def _resolve_next_target(default_endpoint: str) -> str:
    """resolve a safe relative redirect target, falling back to the given endpoint"""
    candidate = request.values.get("next")
    if candidate and candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return _relative_url_for(default_endpoint)


def _resolve_safe_next_value():
    """ログインフォームで利用する安全な next パラメータを取得する。"""
    candidate = request.values.get("next")
    if candidate and candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return None


def _render_login_template():
    return render_template(
        "auth/login.html",
        next_value=_resolve_safe_next_value(),
        passkey_available=True,
    )


def _resolve_current_user_model() -> User | None:
    """現在のログイン状態から永続化されたユーザーモデルを解決する。"""

    actual_user = current_user._get_current_object()  # type: ignore[attr-defined]

    if not isinstance(actual_user, AuthenticatedPrincipal):
        return None

    if actual_user.is_service_account:
        return None

    return db.session.get(User, actual_user.subject_id)


def _pop_role_selection_target() -> str:
    """ロール選択後の遷移先を取得する。"""
    candidate = session.pop("role_selection_next", None) or request.values.get("next")
    if candidate and candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return _relative_url_for("dashboard.dashboard")


def _peek_role_selection_target() -> str | None:
    """ロール選択ページで使用する予定の遷移先を取得する。"""
    candidate = session.get("role_selection_next") or request.args.get("next")
    if candidate and candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return None


def _login_with_domain_user(user, redirect_target=None, *, token=None, token_scope=None):
    """ドメインユーザーが保持するORMモデルでログイン処理を行う。"""
    model = getattr(user, "_model", None)
    if model is None:
        raise ValueError("Domain user is missing attached ORM model for login")
    return _finalize_login_session(
        model,
        _normalize_redirect_target(
            redirect_target,
            fallback=_relative_url_for("dashboard.dashboard"),
        ),
        token=token,
        token_scope=token_scope,
    )


def _finalize_login_session(user_model, redirect_target, *, token=None, token_scope=None):
    if isinstance(user_model, AuthenticatedPrincipal):
        principal = user_model
        roles = list(getattr(principal, "roles", []) or [])
    else:
        # Determine active_role_id BEFORE creating principal
        roles = list(getattr(user_model, "roles", []) or [])
        role_ids = [role.id for role in roles]
        
        # Clear any existing active_role_id for fresh login
        session.pop("active_role_id", None)
        
        # Determine which role should be active
        active_role_id = None
        if len(role_ids) == 1:
            # Single role: auto-select it
            active_role_id = role_ids[0]
            session["active_role_id"] = active_role_id
        elif len(role_ids) > 1:
            # Multiple roles: will need selection (no active role yet)
            active_role_id = None
        
        try:
            principal = TokenService.create_principal_for_user(
                user_model,
                scope=token_scope if token_scope is not None else None,
                active_role_id=active_role_id,
            )
        except ValueError as exc:
            current_app.logger.warning(
                "Failed to construct principal for login session: %s",
                exc,
                extra={"event": "auth.login.principal_error"},
            )
            raise

    login_user(principal)
    g.current_user = principal

    if token_scope is None:
        session.pop(SERVICE_LOGIN_SESSION_KEY, None)
        session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
        g.current_token_scope = None
    else:
        if isinstance(token_scope, set):
            token_scope = list(token_scope)

        if not isinstance(token_scope, (list, tuple)) or not all(
            isinstance(item, str) and item.strip() for item in token_scope
        ):
            raise ValueError("token_scope must be a list of non-empty strings")

        normalized_scope = sorted(item.strip() for item in token_scope)
        session[SERVICE_LOGIN_SESSION_KEY] = True
        g.current_token_scope = set(normalized_scope)

    normalized_redirect = _normalize_redirect_target(
        redirect_target,
        fallback=_relative_url_for("dashboard.dashboard"),
    )

    if len(roles) > 1:
        session["role_selection_next"] = normalized_redirect
        response = redirect(_relative_url_for("auth.select_role"))
    else:
        response = redirect(normalized_redirect)

    if token_scope is None:
        response.delete_cookie("access_token")
    elif token:
        response.set_cookie(
            "access_token",
            token,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="Lax",
        )

    return response


def _extract_access_token() -> str | None:
    token_param = request.values.get("access_token")
    if isinstance(token_param, str):
        candidate = token_param.strip()
        if candidate:
            return candidate

    auth_header = request.headers.get("Authorization", "")
    if isinstance(auth_header, str) and auth_header.lower().startswith("bearer "):
        candidate = auth_header.split(" ", 1)[1].strip()
        if candidate:
            return candidate

    return None


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


def _clear_passkey_registration_session():
    keys_to_clear = [
        PASSKEY_REGISTRATION_CHALLENGE_KEY,
        PASSKEY_REGISTRATION_USER_ID_KEY,
        "passkey_registration_timestamp",
    ]
    for key in keys_to_clear:
        session.pop(key, None)


def _clear_passkey_auth_session():
    keys_to_clear = [PASSKEY_AUTH_CHALLENGE_KEY, "passkey_auth_timestamp"]
    for key in keys_to_clear:
        session.pop(key, None)


def _resolve_safe_redirect(default_endpoint: str, candidate: str | None) -> str:
    if candidate and isinstance(candidate, str) and candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return _relative_url_for(default_endpoint)


def _complete_registration(user):
    """ユーザー登録完了後の共通処理"""
    flash(_("Registration successful"), "success")
    dashboard_url = _relative_url_for("dashboard.dashboard")
    redirect_response = _login_with_domain_user(user, dashboard_url)
    if redirect_response:
        return redirect_response
    return redirect(dashboard_url)


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
        return _redirect_to("auth.register")
    return render_template(template_name, **template_kwargs)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _redirect_to("dashboard.dashboard")
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        token = request.form.get("token")
        user_model = auth_service.authenticate(email, password)
        if not user_model:
            flash(_("Invalid email or password"), "error")
            return _render_login_template()
        if user_model.totp_secret:
            if not token or not verify_totp(user_model.totp_secret, token):
                flash(_("Invalid authentication code"), "error")
                return _render_login_template()
        redirect_target = _resolve_post_login_target()
        return _finalize_login_session(user_model, redirect_target)
    return _render_login_template()


@bp.post("/passkey/options/register")
@login_required
def passkey_registration_options():
    current_app.logger.info(
        "Passkey registration options request received",
        extra={
            "event": "auth.passkey_register",
            "path": request.path,
            "method": request.method,
            "user_id": getattr(current_user, "id", None),
            "service_account": bool(getattr(current_user, "is_service_account", False)),
        },
    )

    if getattr(current_user, "is_service_account", False):
        return jsonify({"error": "not_supported"}), 403

    user_model = _resolve_current_user_model()
    if user_model is None:
        current_app.logger.warning(
            "Passkey registration requested but persistent user missing",
            extra={"event": "auth.passkey_register", "path": request.path},
        )
        return jsonify({"error": "not_supported"}), 403

    try:
        rp_id = _resolve_passkey_rp_id()
        options, challenge = passkey_service.generate_registration_options(
            user_model,
            rp_id=rp_id,
        )
    except Exception:  # pragma: no cover - unexpected failure
        current_app.logger.exception(
            "Failed to prepare passkey registration options",
            extra={"event": "auth.passkey_register", "path": request.path},
        )
        return jsonify({"error": "options_unavailable"}), 500

    session[PASSKEY_REGISTRATION_CHALLENGE_KEY] = challenge
    session[PASSKEY_REGISTRATION_USER_ID_KEY] = current_user.id
    _set_session_timestamp("passkey_registration")
    session.modified = True
    return jsonify(options)


@bp.post("/passkey/verify/register")
@login_required
def passkey_verify_register():
    current_app.logger.info(
        "Passkey registration verification request received",
        extra={
            "event": "auth.passkey_register",
            "path": request.path,
            "method": request.method,
            "user_id": getattr(current_user, "id", None),
        },
    )

    if getattr(current_user, "is_service_account", False):
        _clear_passkey_registration_session()
        return jsonify({"error": "not_supported"}), 403

    if _is_session_expired("passkey_registration"):
        _clear_passkey_registration_session()
        return jsonify({"error": "challenge_expired"}), 400

    challenge = session.get(PASSKEY_REGISTRATION_CHALLENGE_KEY)
    expected_user_id = session.get(PASSKEY_REGISTRATION_USER_ID_KEY)
    if not challenge or expected_user_id != current_user.id:
        _clear_passkey_registration_session()
        return jsonify({"error": "challenge_missing"}), 400

    payload = request.get_json(silent=True) or {}
    credential_payload = _extract_passkey_credential_payload(
        payload,
        meta_keys={"label", "name"},
        required_keys={"id", "rawId", "response"},
    )
    if not isinstance(credential_payload, dict):
        root_keys, credential_keys, response_keys = _gather_passkey_payload_keys(
            payload,
            meta_keys={"label", "name"},
        )
        current_app.logger.warning(
            "Passkey registration payload invalid",
            extra={
                "event": "auth.passkey_register",
                "path": request.path,
                "received_keys": root_keys,
                "credential_keys": credential_keys,
                "response_keys": response_keys,
                "has_credential_key": isinstance(payload, dict)
                and "credential" in payload,
            },
        )
        _clear_passkey_registration_session()
        return jsonify({"error": "invalid_payload"}), 400

    user_model = _resolve_current_user_model()
    if user_model is None:
        _clear_passkey_registration_session()
        current_app.logger.warning(
            "Passkey registration verification failed: persistent user missing",
            extra={"event": "auth.passkey_register", "path": request.path},
        )
        return jsonify({"error": "not_supported"}), 403

    transports = None
    if isinstance(credential_payload, dict):
        response_section = credential_payload.get("response")
        if isinstance(response_section, dict):
            transports = response_section.get("transports")

    label_raw = payload.get("label")
    if label_raw is None:
        label_raw = payload.get("name")
    label = None
    if isinstance(label_raw, str):
        stripped = label_raw.strip()
        if stripped:
            label = stripped

    client_data_details = _extract_passkey_client_data_details(credential_payload)

    try:
        rp_id = _resolve_passkey_rp_id()
        origin = _resolve_passkey_origin()
        record = passkey_service.register_passkey(
            user=user_model,
            payload=json.dumps(credential_payload).encode("utf-8"),
            expected_challenge=challenge,
            transports=transports,
            name=label,
            expected_rp_id=rp_id,
            expected_origin=origin,
        )
    except PasskeyRegistrationError as exc:
        _clear_passkey_registration_session()
        trace_payload = _build_passkey_trace_payload(
            cause=_format_exception_chain(exc),
            expected_challenge=challenge,
            client_data_details=client_data_details,
            expected_rp_id=rp_id,
            expected_origin=origin,
        )
        current_app.logger.warning(
            "Passkey registration verification failed",
            extra={
                "event": "auth.passkey_register",
                "path": request.path,
                "reason": exc.args[0] if exc.args else "verification_failed",
                "trace": trace_payload,
            },
        )
        return (
            jsonify({"error": exc.args[0] if exc.args else "verification_failed"}),
            400,
        )
    except Exception:
        _clear_passkey_registration_session()
        current_app.logger.exception(
            "Unexpected error during passkey registration",
            extra={"event": "auth.passkey_register", "path": request.path},
        )
        return jsonify({"error": "internal_error"}), 500

    _clear_passkey_registration_session()

    passkey_payload = {
        "id": record.id,
        "name": record.name,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "last_used_at": record.last_used_at.isoformat() if record.last_used_at else None,
        "transports": record.transports or [],
        "backup_eligible": bool(getattr(record, "backup_eligible", False)),
        "backup_state": bool(getattr(record, "backup_state", False)),
    }
    return jsonify({"result": "ok", "passkey": passkey_payload})


@bp.post("/passkey/options/login")
def passkey_login_options():
    payload = request.get_json(silent=True)
    email_value = None
    if isinstance(payload, dict):
        raw_email = payload.get("email")
        if isinstance(raw_email, str):
            stripped = raw_email.strip()
            if stripped:
                email_value = stripped

    if email_value is None:
        form_email = request.form.get("email")
        if isinstance(form_email, str):
            stripped = form_email.strip()
            if stripped:
                email_value = stripped

    user_model = None
    if email_value:
        stmt = select(User).where(User.email == email_value)
        user_model = db.session.execute(stmt).scalar_one_or_none()

    current_app.logger.info(
        "Passkey login options request received",
        extra={
            "event": "auth.passkey_login",
            "path": request.path,
            "method": request.method,
            "user_id": getattr(current_user, "id", None),
            "lookup_email": email_value,
            "resolved_user_id": getattr(user_model, "id", None),
        },
    )

    try:
        rp_id = _resolve_passkey_rp_id()
        options, challenge = passkey_service.generate_authentication_options(
            user=user_model,
            rp_id=rp_id,
        )
    except Exception:  # pragma: no cover - unexpected failure
        current_app.logger.exception(
            "Failed to prepare passkey authentication options",
            extra={"event": "auth.passkey_login", "path": request.path},
        )
        return jsonify({"error": "options_unavailable"}), 500

    session[PASSKEY_AUTH_CHALLENGE_KEY] = challenge
    _set_session_timestamp("passkey_auth")
    session.modified = True
    return jsonify(options)


@bp.post("/passkey/verify/login")
def passkey_verify_login():
    current_app.logger.info(
        "Passkey authentication request received",
        extra={
            "event": "auth.passkey_login",
            "path": request.path,
            "method": request.method,
            "user_id": getattr(current_user, "id", None),
        },
    )

    if _is_session_expired("passkey_auth"):
        _clear_passkey_auth_session()
        return jsonify({"error": "challenge_expired"}), 400

    challenge = session.get(PASSKEY_AUTH_CHALLENGE_KEY)
    if not challenge:
        return jsonify({"error": "challenge_missing"}), 400

    payload = request.get_json(silent=True) or {}
    credential_payload = _extract_passkey_credential_payload(
        payload,
        meta_keys={"next"},
        required_keys={"id", "rawId", "response"},
    )
    if not isinstance(credential_payload, dict):
        root_keys, credential_keys, response_keys = _gather_passkey_payload_keys(
            payload,
            meta_keys={"next"},
        )
        current_app.logger.warning(
            "Passkey authentication payload invalid",
            extra={
                "event": "auth.passkey_login",
                "path": request.path,
                "received_keys": root_keys,
                "credential_keys": credential_keys,
                "response_keys": response_keys,
                "has_credential_key": isinstance(payload, dict)
                and "credential" in payload,
            },
        )
        _clear_passkey_auth_session()
        return jsonify({"error": "invalid_payload"}), 400

    try:
        rp_id = _resolve_passkey_rp_id()
        origin = _resolve_passkey_origin()
        user_model = passkey_service.authenticate(
            payload=json.dumps(credential_payload).encode("utf-8"),
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
        )
    except PasskeyAuthenticationError as exc:
        _clear_passkey_auth_session()
        current_app.logger.warning(
            "Passkey authentication failed",
            extra={
                "event": "auth.passkey_login",
                "path": request.path,
                "reason": exc.args[0] if exc.args else "verification_failed",
            },
        )
        return (
            jsonify({"error": exc.args[0] if exc.args else "verification_failed"}),
            401,
        )
    except Exception:
        _clear_passkey_auth_session()
        current_app.logger.exception(
            "Unexpected error during passkey authentication",
            extra={"event": "auth.passkey_login", "path": request.path},
        )
        return jsonify({"error": "internal_error"}), 500

    _clear_passkey_auth_session()

    if not getattr(user_model, "is_active", True):
        current_app.logger.warning(
            "Passkey authentication rejected for inactive user",
            extra={
                "event": "auth.passkey_login",
                "path": request.path,
                "user_id": getattr(user_model, "id", None),
            },
        )
        return jsonify({"error": "account_inactive"}), 403

    available_permissions = sorted(getattr(user_model, "all_permissions", []) or [])
    granted_scope = list(available_permissions)

    session[API_LOGIN_SCOPE_SESSION_KEY] = normalize_scope_items(granted_scope)

    try:
        access_token, refresh_token = TokenService.generate_token_pair(
            user_model, granted_scope
        )
    except Exception:
        current_app.logger.exception(
            "Failed to issue token pair for passkey login",
            extra={"event": "auth.passkey_login", "path": request.path},
        )
        return jsonify({"error": "token_issue_failed"}), 500

    raw_next = payload.get("next")
    redirect_target = _resolve_safe_redirect("dashboard.dashboard", raw_next)
    roles = list(getattr(user_model, "roles", []) or [])
    requires_role_selection = len(roles) > 1

    _finalize_login_session(user_model, redirect_target)

    if requires_role_selection:
        redirect_url = url_for("auth.select_role", next=redirect_target)
    else:
        redirect_url = redirect_target

    response_payload = {
        "result": "ok",
        "redirect_url": redirect_url,
        "requires_role_selection": requires_role_selection,
        "available_scopes": available_permissions,
        "scope": " ".join(granted_scope),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "email": getattr(user_model, "email", None),
    }

    response = jsonify(response_payload)
    apply_gui_access_cookie(response, access_token, granted_scope)
    return response


@bp.post("/passkey/<int:credential_id>/delete")
@login_required
def delete_passkey(credential_id: int):
    if getattr(current_user, "is_service_account", False):
        return jsonify({"error": "not_supported"}), 403

    user_model = _resolve_current_user_model()
    if user_model is None:
        current_app.logger.warning(
            "Passkey deletion requested but user could not be resolved",
            extra={"event": "auth.passkey_delete", "path": request.path},
        )
        return jsonify({"error": "not_supported"}), 403

    record = passkey_repo.find_for_user(user_model.id, credential_id)
    if record is None:
        return jsonify({"error": "not_found"}), 404

    passkey_repo.delete(record)
    return jsonify({"result": "ok"})


@bp.route("/servicelogin", methods=["GET", "POST"])
def service_login():
    redirect_target = _resolve_next_target("dashboard.dashboard")

    if current_user.is_authenticated and not getattr(current_user, "is_service_account", False):
        return redirect(redirect_target)

    token = _extract_access_token()
    if not token:
        current_app.logger.warning(
            "Service login request rejected: missing access token",
            extra={"event": "auth.service_login", "path": request.path},
        )
        session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
        return make_response(_("Access token is required"), 400)

    principal = TokenService.create_principal_from_token(token)
    if not principal:
        current_app.logger.warning(
            "Service login token verification failed",
            extra={"event": "auth.service_login", "path": request.path},
        )
        session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
        return make_response(_("Invalid access token"), 401)


    if not principal.is_service_account:
        current_app.logger.warning(
            "Service login token rejected: subject type is not a service account",
            extra={"event": "auth.service_login", "path": request.path},
        )
        session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
        return make_response(_("Invalid access token"), 401)
    current_app.logger.info(
        "Service login successful",
        extra={
            "event": "auth.service_login",
            "path": request.path,
            "service_account_id": principal.id,
            "actor": principal.display_name,
            "redirect": redirect_target,
            "roles": [],
        },
    )

    session.pop("active_role_id", None)

    normalized_scope = sorted(item.strip() for item in principal.scope if item)
    session[SERVICE_LOGIN_SESSION_KEY] = True
    session[SERVICE_LOGIN_TOKEN_SESSION_KEY] = token
    g.current_token_scope = set(principal.scope)

    g.current_user = principal
    login_user(principal)

    response = redirect(redirect_target)

    if token:
        response.set_cookie(
            "access_token",
            token,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="Lax",
        )
    else:
        response.delete_cookie("access_token")

    session.modified = True
    return response


@bp.route("/select-role", methods=["GET", "POST"])
@login_required
def select_role():
    roles = list(getattr(current_user, "roles", []) or [])
    if len(roles) <= 1:
        _sync_active_role(current_user)
        return redirect(_pop_role_selection_target())

    if request.method == "POST":
        role_choice = request.form.get("active_role")
        available_roles = {str(role.id): role for role in roles}
        if role_choice and role_choice in available_roles:
            session["active_role_id"] = available_roles[role_choice].id
            session.modified = True
            
            # Reload the principal with the selected role's permissions
            user_model = _resolve_current_user_model()
            if user_model is not None:
                try:
                    refreshed = TokenService.create_principal_for_user(
                        user_model,
                        active_role_id=available_roles[role_choice].id
                    )
                    login_user(refreshed)
                    g.current_user = refreshed
                except ValueError:
                    pass
            
            flash(
                _(
                    "Active role switched to %(role)s.",
                    role=available_roles[role_choice].name,
                ),
                "success",
            )
            return redirect(_pop_role_selection_target())

        message = _("Invalid role selection.")
        with force_locale("en"):
            english_message = _("Invalid role selection.")
        if english_message and english_message != message:
            message = f"{message} ({english_message})"
        flash(message, "error")

    selected_role_id = session.get("active_role_id")
    return render_template(
        "auth/select_role.html",
        roles=roles,
        selected_role_id=selected_role_id,
        next_target=_peek_role_selection_target(),
    )

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
            return _redirect_to("auth.register_totp")
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
        return _redirect_to("auth.register")
    
    # ユーザーを取得
    user_model = db.session.get(User, user_id)
    if not user_model or user_model.is_active:
        _clear_registration_session()
        flash(_("Registration session invalid. Please register again."), "error")
        return _redirect_to("auth.register")
    
    uri = provisioning_uri(user_model.email, secret)
    qr_data = qr_code_data_uri(uri)
    
    if request.method == "POST":
        token = request.form.get("token")
        if not token or not verify_totp(secret, token):
            flash(_("Invalid authentication code"), "error")
            return render_template(
                "auth/register_totp.html",
                qr_data=qr_data,
                secret=secret,
                otpauth_uri=uri,
            )
        
        try:
            # ユーザーをTOTPと共にアクティブ化
            domain_user = user_repo._to_domain(user_model)
            u = auth_service.activate_user_with_totp(domain_user, secret)

            _clear_registration_session()
            flash(_("Registration successful"), "success")
            dashboard_url = url_for("dashboard.dashboard")
            redirect_response = _login_with_domain_user(u, dashboard_url)
            if redirect_response:
                return redirect_response
            return redirect(dashboard_url)
        except Exception as e:
            flash(_("Registration failed: {}").format(str(e)), "error")
            return render_template(
                "auth/register_totp.html",
                qr_data=qr_data,
                secret=secret,
                otpauth_uri=uri,
            )

    return render_template(
        "auth/register_totp.html",
        qr_data=qr_data,
        secret=secret,
        otpauth_uri=uri,
    )


@bp.route("/register/totp/cancel", methods=["POST"])
def register_totp_cancel():
    """2FA登録をキャンセルして、非アクティブユーザーを削除"""
    user_id = session.get("reg_user_id")
    
    if user_id:
        # 非アクティブユーザーを削除
        user_model = db.session.get(User, user_id)
        if user_model and not user_model.is_active:
            domain_user = user_repo._to_domain(user_model)
            user_repo.delete(domain_user)
    
    _clear_registration_session()
    flash(_("Registration cancelled. You can start over."), "info")
    return _redirect_to("auth.register")


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
    is_service_account = bool(getattr(current_user, "is_service_account", False))
    user_model = _resolve_current_user_model()
    if not is_service_account and user_model is None:
        current_app.logger.warning(
            "Profile requested but persistent user could not be resolved",
            extra={"event": "auth.profile.user_missing", "path": request.path},
        )
        flash(_("We could not load your account information. Please sign in again."), "error")
        logout_user()
        return _redirect_to("auth.login")

    languages_iterable = list(settings.languages)
    languages = [lang for lang in languages_iterable if lang]
    if not languages:
        languages = [settings.babel_default_locale or "en"]
    language_labels = {
        "ja": _("Japanese"),
        "en": _("English"),
    }
    default_language = settings.babel_default_locale or languages[0]
    if default_language not in language_labels:
        language_labels[default_language] = default_language

    fallback_language = languages[0] if languages else default_language
    selected_language = request.cookies.get("lang") or fallback_language or default_language
    if selected_language not in languages:
        selected_language = fallback_language or default_language

    default_timezone = settings.babel_default_timezone
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

    raw_roles = list(getattr(user_model, "roles", []) or []) if user_model else []
    role_options = [
        role
        for role in raw_roles
        if hasattr(role, "id") and getattr(role, "id", None) is not None
    ]
    if request.method == "POST":
        action = request.form.get("action", "update-preferences")
        if action == "switch-role":
            role_choice = request.form.get("active_role")
            available_roles = {str(role.id): role for role in role_options}

            if role_choice and role_choice in available_roles:
                session["active_role_id"] = available_roles[role_choice].id
                session.modified = True
                
                # Reload the principal with the new active role
                if user_model is not None:
                    try:
                        refreshed = TokenService.create_principal_for_user(
                            user_model,
                            active_role_id=available_roles[role_choice].id
                        )
                        login_user(refreshed)
                        g.current_user = refreshed
                    except ValueError:
                        pass
                
                flash(_("Active role switched to %(role)s.", role=available_roles[role_choice].name), "success")
                return redirect(_relative_url_for("auth.profile"))

            if not role_options:
                flash(_("Role switching is not available for this account."), "error")
                return redirect(_relative_url_for("auth.profile"))

            flash(_("Invalid role selection."), "error")
            return redirect(_relative_url_for("auth.profile"))

        form_lang = request.form.get("language")
        form_tz = request.form.get("timezone")
        response = redirect(_relative_url_for("auth.profile"))
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
        "Asia/Shanghai": _("Asia/Shanghai (China)"),
        "Asia/Singapore": _("Asia/Singapore (Singapore)"),
        "Australia/Sydney": _("Australia/Sydney (Australia)"),
        "Europe/London": _("Europe/London (UK)"),
        "America/New_York": _("America/New York (USA, Eastern Time)"),
        "America/Chicago": _("America/Chicago (USA, Central Time)"),
        "America/Los_Angeles": _("America/Los Angeles (USA, Pacific Time)"),
    }

    if default_timezone not in timezone_labels:
        timezone_labels[default_timezone] = default_timezone
    timezone_choices = []
    for code in timezone_codes:
        label = timezone_labels.get(code)
        if not label:
            label = code
        timezone_choices.append({"code": code, "label": label})

    current_permissions = getattr(current_user, "permissions", set())
    normalized_permissions = {
        str(code).strip()
        for code in current_permissions or []
        if isinstance(code, str) and code.strip()
    }
    active_permissions = sorted(normalized_permissions)
    passkey_credentials: list = []
    if not is_service_account and user_model is not None:
        try:
            passkey_credentials = passkey_repo.list_for_user(user_model.id)
        except Exception:
            current_app.logger.exception(
                "Failed to load passkey credentials for profile",
                extra={"event": "auth.profile.passkeys", "path": request.path},
            )

    return render_template(
        "auth/profile.html",
        language_choices=language_choices,
        selected_language=selected_language,
        timezone_choices=timezone_choices,
        selected_timezone=selected_timezone,
        server_time_utc=server_time_utc,
        localized_time=localized_time,
        active_role=getattr(current_user, "active_role", None),
        role_options=role_options,
        is_service_account=is_service_account,
        active_permissions=active_permissions,
        passkey_credentials=passkey_credentials,
    )


@bp.route("/edit", methods=["GET", "POST"])
@login_required
def edit():
    is_service_account = bool(getattr(current_user, "is_service_account", False))
    if is_service_account:
        flash(_("Service accounts cannot edit profile details."), "warning")
        return _redirect_to("auth.profile")

    user_model = _resolve_current_user_model()
    if user_model is None:
        current_app.logger.warning(
            "Profile edit requested but persistent user missing",
            extra={"event": "auth.profile.edit", "path": request.path},
        )
        flash(_("We could not load your account information. Please sign in again."), "error")
        logout_user()
        return _redirect_to("auth.login")

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        if not email:
            flash(_("Email is required"), "error")
            return render_template("auth/edit.html", is_service_account=is_service_account)
        if email != user_model.email and User.query.filter_by(email=email).first():
            flash(_("Email already exists"), "error")
            return render_template("auth/edit.html", is_service_account=is_service_account)
        user_model.email = email
        if password:
            user_model.set_password(password)
        db.session.commit()

        try:
            active_role_id = session.get("active_role_id")
            refreshed = TokenService.create_principal_for_user(user_model, active_role_id=active_role_id)
        except ValueError:
            refreshed = None

        if refreshed is not None:
            login_user(refreshed)
            g.current_user = refreshed

        flash(_("Profile updated"), "success")
        return _redirect_to("auth.profile")
    return render_template("auth/edit.html", is_service_account=is_service_account, user=user_model)


@bp.route("/setup_totp", methods=["GET", "POST"])
@login_required
def setup_totp():
    next_url = _resolve_next_target("auth.edit")
    service_redirect = _resolve_next_target("dashboard.dashboard")
    is_service_account = bool(getattr(current_user, "is_service_account", False))

    if is_service_account:
        flash(_("Two-factor authentication is not available for service accounts."), "warning")
        target = _normalize_redirect_target(
            service_redirect,
            fallback=_relative_url_for("dashboard.dashboard"),
        )
        return redirect(target)

    user_model = _resolve_current_user_model()
    if user_model is None:
        current_app.logger.warning(
            "TOTP setup requested but no persistent user could be resolved",
            extra={"event": "auth.totp.user_missing"},
        )
        flash(_("We could not load your account information. Please sign in again."), "error")
        logout_user()
        return _redirect_to("auth.login")

    if user_model.totp_secret:
        flash(_("Two-factor authentication already configured"), "error")
        return redirect(next_url)

    secret = session.get("setup_totp_secret")

    # セッション有効性をチェック
    if secret and _is_session_expired("setup_totp"):
        _clear_setup_totp_session()
        secret = None
    
    if not secret:
        secret = new_totp_secret()
        session["setup_totp_secret"] = secret
        _set_session_timestamp("setup_totp")
    
    uri = provisioning_uri(user_model.email, secret)
    qr_data = qr_code_data_uri(uri)
    
    if request.method == "POST":
        token = request.form.get("token")
        if not token or not verify_totp(secret, token):
            flash(_("Invalid authentication code"), "error")
            return render_template(
                "auth/setup_totp.html",
                qr_data=qr_data,
                secret=secret,
                otpauth_uri=uri,
                next_url=next_url,
            )
        user_model.totp_secret = secret
        db.session.commit()
        try:
            active_role_id = session.get("active_role_id")
            refreshed = TokenService.create_principal_for_user(user_model, active_role_id=active_role_id)
        except ValueError:
            refreshed = None
        if refreshed is not None:
            login_user(refreshed)
            g.current_user = refreshed
        _clear_setup_totp_session()
        flash(_("Two-factor authentication enabled"), "success")
        return redirect(next_url)
    return render_template(
        "auth/setup_totp.html",
        qr_data=qr_data,
        secret=secret,
        otpauth_uri=uri,
        next_url=next_url,
    )

@bp.route("/setup_totp/cancel", methods=["POST"])
@login_required
def setup_totp_cancel():
    """2FA設定をキャンセル"""
    _clear_setup_totp_session()
    flash(_("Two-factor authentication setup cancelled."), "info")
    next_url = _resolve_next_target("auth.edit")
    return redirect(next_url)

@bp.route("/logout")
@login_required
def logout():
    user = current_user._get_current_object()
    user_payload = {
        "message": "User logged out",
        "subject_type": getattr(user, "subject_type", None),
        "subject_id": getattr(user, "subject_id", None),
        "user_id": getattr(user, "user_id", None),
        "service_account_id": getattr(user, "service_account_id", None),
        "name": getattr(user, "name", None),
        "display_name": getattr(user, "display_name", None),
        "email": getattr(user, "email", None),
    }

    user_payload = {key: value for key, value in user_payload.items() if value is not None}

    TokenService.revoke_refresh_token(user)
    logout_user()
    session.pop("picker_session_id", None)
    session.pop("active_role_id", None)
    session.pop(SERVICE_LOGIN_SESSION_KEY, None)
    session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)

    response = redirect(_relative_url_for("index"))
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
        return _redirect_to("admin.google_accounts")

    code = request.args.get("code")
    state = request.args.get("state")
    saved = session.get("google_oauth_state") or {}
    if not code or state != saved.get("state"):
        flash(_("Invalid OAuth state."), "error")
        return _redirect_to("admin.google_accounts")

    callback_scheme = determine_external_scheme()
    callback_url = url_for(
        "auth.google_oauth_callback", _external=True, _scheme=callback_scheme
    )

    token_data = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": callback_url,
        "grant_type": "authorization_code",
    }

    # デバッグログを追加
    current_app.logger.info(f"OAuth callback - client_id: {token_data['client_id']}")
    current_app.logger.info(f"OAuth callback - client_secret exists: {bool(token_data['client_secret'])}")
    current_app.logger.info(
        "OAuth callback - redirect_uri: %s", token_data["redirect_uri"]
    )

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
            return _redirect_to("admin.google_accounts")
    except Exception as e:
        current_app.logger.error(f"Failed to obtain token from Google: {str(e)}")
        flash(_("Failed to obtain token from Google: %(msg)s", msg=str(e)), "error")
        return _redirect_to("admin.google_accounts")

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
        return _redirect_to("admin.google_accounts")

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
        return _redirect_to("admin.google_accounts")
    return _redirect_to("auth.picker", account_id=account.id)

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
        return _redirect_to("admin.google_accounts")

    access_token = tokens.get("access_token")
    if not access_token:
        flash(_("Failed to obtain access token."), "error")
        return _redirect_to("admin.google_accounts")

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
        return _redirect_to("admin.google_accounts")
    except ValueError:
        flash(_("Invalid response from picker API."), "error")
        return _redirect_to("admin.google_accounts")

    picker_uri = picker_data.get("pickerUri")
    if not picker_uri:
        msg = picker_data.get("error") or _("Failed to create picker session.")
        flash(msg, "error")
        return _redirect_to("admin.google_accounts")

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
    return _redirect_to("admin.google_accounts")


@bp.route("/password/forgot", methods=["GET", "POST"])
def password_forgot():
    """パスワードリセットメール送信画面。"""
    if current_user.is_authenticated:
        return _redirect_to("dashboard.dashboard")
    
    if request.method == "POST":
        email = request.form.get("email")
        if not email:
            flash(_("Email address is required"), "error")
            return render_template("auth/password_forgot.html")
        
        from webapp.services.password_reset_service import PasswordResetService
        
        # パスワードリセットリクエストを作成
        success, error_message = PasswordResetService.create_reset_request(email)
        
        if not success and error_message:
            # メール機能が無効な場合のみエラーを表示
            flash(error_message, "error")
            return render_template("auth/password_forgot.html")
        
        # セキュリティ: 常に成功メッセージを返す（アカウント存在確認攻撃を防ぐ）
        flash(
            _("If an account exists with that email address, you will receive a password reset link. Please check your spam folder if you don't see it."),
            "success"
        )
        return _redirect_to("auth.login")
    
    return render_template("auth/password_forgot.html")


@bp.route("/password/reset", methods=["GET", "POST"])
def password_reset():
    """パスワードリセット画面。"""
    if current_user.is_authenticated:
        return _redirect_to("dashboard.dashboard")
    
    token = request.args.get("token") or request.form.get("token")
    if not token:
        flash(_("Invalid or missing reset token"), "error")
        return _redirect_to("auth.login")
    
    from webapp.services.password_reset_service import PasswordResetService
    
    # トークンの検証（GETリクエストでも検証して早期にエラーを表示）
    if request.method == "GET":
        email = PasswordResetService.verify_token(token)
        if not email:
            flash(_("This password reset link is invalid or has expired"), "error")
            return _redirect_to("auth.login")
    
    if request.method == "POST":
        password = request.form.get("password")
        password_confirm = request.form.get("password_confirm")
        
        if not password or not password_confirm:
            flash(_("Both password fields are required"), "error")
            return render_template("auth/password_reset.html", token=token)
        
        if password != password_confirm:
            flash(_("Passwords do not match"), "error")
            return render_template("auth/password_reset.html", token=token)
        
        if len(password) < 8:
            flash(_("Password must be at least 8 characters long"), "error")
            return render_template("auth/password_reset.html", token=token)
        
        # パスワードリセット実行
        success = PasswordResetService.reset_password(token, password)
        if success:
            flash(_("Your password has been reset successfully. Please log in with your new password."), "success")
            return _redirect_to("auth.login")
        else:
            flash(_("This password reset link is invalid or has expired"), "error")
            return _redirect_to("auth.login")
    
    return render_template("auth/password_reset.html", token=token)
