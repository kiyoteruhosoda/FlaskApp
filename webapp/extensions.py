from core.db import db
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_babel import Babel
from flask_babel import lazy_gettext as _l
from flask import current_app, g
from flask_smorest import Api

from shared.application.authenticated_principal import AuthenticatedPrincipal

migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"  # 未ログイン時のリダイレクト先
babel = Babel()
api = Api()

login_manager.login_message = None


@login_manager.user_loader
def load_user(user_id):
    from core.models.user import User
    from core.models.service_account import ServiceAccount

    if isinstance(user_id, str) and user_id.startswith("system:"):
        try:
            _, raw_id = user_id.split(":", 1)
            account_id = int(raw_id)
        except (ValueError, AttributeError):
            return None
        account = ServiceAccount.query.get(account_id)
        if not account or not account.is_active():
            return None
        return AuthenticatedPrincipal(
            subject_type="system",
            subject_id=account.service_account_id,
            identifier=f"s+{account.service_account_id}",
            scope=frozenset(account.scopes),
            display_name=account.name,
        )

    try:
        numeric_id = int(user_id)
    except (TypeError, ValueError):
        return None

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

    principal = TokenService.verify_access_token(token)
    if not principal:
        current_app.logger.debug(
            "JWT token verification failed in request_loader",
            extra={"event": "auth.jwt.invalid"},
        )
        return None

    g.current_token_scope = set(principal.scope)
    g.current_user = principal

    return principal

