from core.db import db
from flask_migrate import Migrate
from flask_login import LoginManager, AnonymousUserMixin
from flask_babel import Babel
from flask_babel import lazy_gettext as _l
from flask import current_app, g, session
from flask_mailman import Mail

from presentation.web.openapi.smorest_ext import Api

migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = None
babel = Babel()
api = Api()
mail = Mail()

login_manager.login_message = None


class AnonymousUser(AnonymousUserMixin):
    """未認証ユーザー。権限チェック ``can()`` を常に ``False`` で返す。

    ``current_user.can(...)`` を認証状態に関わらず安全に呼べるようにする
    （未認証時に AttributeError とならないため）。
    """

    def can(self, *codes: str) -> bool:
        return False


login_manager.anonymous_user = AnonymousUser


@login_manager.user_loader
def load_user(user_id):
    from core.models.user import User
    from presentation.web.services.token_service import TokenService

    # Service accounts are stateless — they authenticate per-request via Bearer tokens.
    # Session-based service account authentication is no longer supported.
    if isinstance(user_id, str) and user_id.startswith("system:"):
        return None

    try:
        numeric_id = int(user_id.split(":", 1)[1] if ":" in str(user_id) else user_id)
    except (TypeError, ValueError):
        return None

    user = db.session.get(User, numeric_id)
    if not user:
        return None

    if not getattr(user, "is_active", True):
        return None

    try:
        active_role_id = session.get("active_role_id")
        principal = TokenService.create_principal_for_user(user, active_role_id=active_role_id)
    except ValueError:
        current_app.logger.warning(
            "Failed to create principal for user in user_loader",
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
    from presentation.web.services.token_service import TokenService

    principal = TokenService.create_principal_from_token(token)
    if not principal:
        current_app.logger.debug(
            "JWT token verification failed in request_loader",
            extra={"event": "auth.jwt.invalid"},
        )
        return None

    g.current_token_scope = set(principal.scope)
    g.current_user = principal

    return principal

