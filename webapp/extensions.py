from core.db import db
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_babel import Babel
from flask_babel import lazy_gettext as _l
from flask import current_app, g, session

from webapp.auth import SERVICE_LOGIN_TOKEN_SESSION_KEY
from flask_smorest import Api

migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"  # 未ログイン時のリダイレクト先
babel = Babel()
api = Api()

login_manager.login_message = None


@login_manager.user_loader
def load_user(user_id):
    from core.models.user import User
    from webapp.services.token_service import TokenService

    subject_type: str | None = None
    raw_identifier = user_id

    if isinstance(user_id, str) and ":" in user_id:
        subject_type, raw_identifier = user_id.split(":", 1)
    elif isinstance(user_id, str):
        subject_type = "individual"
    else:
        subject_type = "individual"

    if subject_type == "system":
        try:
            account_id = int(raw_identifier)
        except (TypeError, ValueError):
            return None

        token = session.get(SERVICE_LOGIN_TOKEN_SESSION_KEY)
        if not token:
            return None

        principal = TokenService.create_principal_from_token(token)
        if not principal or not principal.is_service_account:
            session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
            return None
        if principal.subject_id != account_id:
            session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
            return None

        g.current_user = principal
        return principal

    try:
        numeric_id = int(raw_identifier)
    except (TypeError, ValueError):
        return None

    session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
    user = db.session.get(User, numeric_id)
    if not user or not getattr(user, "is_active", True):
        return None

    try:
        active_role_id = session.get("active_role_id")
        principal = TokenService.create_principal_for_user(user, active_role_id=active_role_id)
    except ValueError as exc:
        current_app.logger.warning(
            "Failed to create principal for user in user_loader",  # type: ignore[attr-defined]
            extra={"event": "auth.user_loader.error", "user_id": numeric_id},
        )
        return None

    g.current_user = principal
    return principal


@login_manager.request_loader
def load_user_from_request(request):
    """JWTまたはCookieからユーザーをロード"""
    token = None
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
    elif request.cookies.get("access_token"):
        token = request.cookies.get("access_token")
    if not token:
        return None
    from webapp.services.token_service import TokenService

    principal = TokenService.create_principal_from_token(token)
    if not principal:
        current_app.logger.debug(
            "JWT token verification failed in request_loader",
            extra={"event": "auth.jwt.invalid"},
        )
        return None

    if principal.is_service_account:
        session[SERVICE_LOGIN_TOKEN_SESSION_KEY] = token
    else:
        session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)

    g.current_token_scope = set(principal.scope)
    g.current_user = principal

    return principal

