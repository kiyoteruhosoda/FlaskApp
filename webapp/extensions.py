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

    if isinstance(user_id, str) and user_id.startswith("system:"):
        try:
            _, raw_id = user_id.split(":", 1)
            account_id = int(raw_id)
        except (ValueError, AttributeError):
            return None

        token = session.get(SERVICE_LOGIN_TOKEN_SESSION_KEY)
        if not token:
            return None

        from webapp.services.token_service import TokenService

        principal = TokenService.create_principal_from_token(token)
        if not principal or not principal.is_service_account:
            session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
            return None
        if principal.subject_id != account_id:
            session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
            return None

        return principal

    try:
        numeric_id = int(user_id)
    except (TypeError, ValueError):
        return None

    session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
    return User.query.get(numeric_id)


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

