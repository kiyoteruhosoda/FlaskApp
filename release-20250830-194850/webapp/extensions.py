from core.db import db
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_babel import Babel
from flask_babel import lazy_gettext as _l
from flask import current_app
import jwt


migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"  # 未ログイン時のリダイレクト先
babel = Babel()

login_manager.login_message = None


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
    try:
        payload = jwt.decode(
            token,
            current_app.config["JWT_SECRET_KEY"],
            algorithms=["HS256"],
        )
    except jwt.PyJWTError:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    from core.models.user import User

    return User.query.get(user_id)

