"""サービスログイン（サービスアカウント代理ログイン）のリクエストフック.

``create_app()`` に定義されていたサービスログイン関連のフックを切り出す。
アクセストークンからスコープを解決して ``g.current_token_scope`` に載せ、トークン
失効や subject 不一致時にはセッションとログイン状態を破棄してクッキーを除去する。
"""

from __future__ import annotations

from flask import Flask, current_app, g, request, session
from flask_login import current_user, logout_user

from webapp.auth import SERVICE_LOGIN_SESSION_KEY, SERVICE_LOGIN_TOKEN_SESSION_KEY
from webapp.services.token_service import TokenService


def register_service_login_hooks(app: Flask) -> None:
    """サービスログインのスコープ適用とクッキー除去フックを登録する。"""

    @app.before_request
    def _apply_service_login_scope():
        if not session.get(SERVICE_LOGIN_SESSION_KEY):
            return
        if getattr(g, "current_token_scope", None) is not None:
            return

        token = request.cookies.get("access_token")
        if not token:
            g.current_token_scope = set()
            session.pop(SERVICE_LOGIN_SESSION_KEY, None)
            session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
            logout_user()
            g.service_login_clear_cookie = True
            return

        principal = TokenService.create_principal_from_token(token)
        if not principal:
            g.current_token_scope = set()
            session.pop(SERVICE_LOGIN_SESSION_KEY, None)
            session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
            logout_user()
            g.service_login_clear_cookie = True
            return

        principal_scope = principal.scope if principal else frozenset()
        if current_user.is_authenticated and hasattr(current_user, "get_id"):
            current_id = str(current_user.get_id())
            if current_id != str(principal.get_id()):
                current_app.logger.warning(
                    "Service login token subject mismatch; ignoring token scope",
                    extra={"event": "auth.service_login", "path": request.path},
                )
                logout_user()
                session.pop(SERVICE_LOGIN_SESSION_KEY, None)
                session.pop(SERVICE_LOGIN_TOKEN_SESSION_KEY, None)
                g.current_token_scope = set()
                g.service_login_clear_cookie = True
                return

        if principal.is_service_account:
            session[SERVICE_LOGIN_TOKEN_SESSION_KEY] = token
        g.current_token_scope = set(principal_scope)

    @app.after_request
    def _clear_service_login_cookie(response):
        if getattr(g, "service_login_clear_cookie", False):
            response.delete_cookie("access_token")
        return response
