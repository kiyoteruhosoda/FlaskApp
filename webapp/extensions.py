from core.db import db
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_babel import Babel
from flask_babel import lazy_gettext as _l
from flask import current_app, g
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

    return User.query.get(int(user_id))


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

    verification = TokenService.verify_access_token(token)
    if not verification:
        current_app.logger.debug(
            "JWT token verification failed in request_loader",
            extra={"event": "auth.jwt.invalid"},
        )
        return None

    user, scope = verification
    g.current_token_scope = scope

    return user

