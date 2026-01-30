"""Authentication domain controller."""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from flask import Blueprint, current_app, request, session, jsonify
from flask_login import login_user, logout_user, current_user
from flask_babel import gettext as _

from webapp.api.controllers.base_controller import BaseController
from webapp.api.controllers.schemas.auth import (
    LoginRequestSchema,
    LoginResponseSchema, 
    LogoutResponseSchema,
    RefreshRequestSchema,
    RefreshResponseSchema,
    ServiceAccountTokenRequestSchema,
    ServiceAccountTokenResponseSchema,
)
from webapp.services.token_service import TokenService
from webapp.services.gui_access_cookie import (
    API_LOGIN_SCOPE_SESSION_KEY,
    apply_gui_access_cookie,
    clear_gui_access_cookie,
    should_issue_gui_access_cookie,
)
from webapp.auth.service_account_auth import (
    ServiceAccountJWTError,
    ServiceAccountTokenValidator,
)
from webapp.auth.totp import verify_totp
from core.models.user import User
from core.settings import settings


class AuthController(BaseController):
    """認証ドメインコントローラー."""
    
    def _register_routes(self) -> None:
        """認証関連のルートを登録."""
        
        @self.bp.post("/token")
        def service_account_token_exchange():
            """サービスアカウントトークン交換."""
            data = request.get_json() or {}
            return self._handle_service_account_token(data)
        
        @self.bp.post("/login")
        def login():
            """ユーザーログイン."""
            data = request.get_json() or {}
            return self._handle_login(data)
        
        @self.bp.post("/logout")
        def logout():
            """ユーザーログアウト."""
            return self._handle_logout()
        
        @self.bp.post("/refresh")
        def refresh_token():
            """トークンリフレッシュ."""
            data = request.get_json() or {}
            return self._handle_refresh(data)
        
        @self.bp.get("/auth/check")
        def auth_check():
            """認証状態確認."""
            return self._handle_auth_check()
    
    def _handle_service_account_token(self, data: dict) -> dict:
        """サービスアカウントトークン処理."""
        self._log_action("service_account_token_request")
        
        grant_type = data.get("grant_type")
        JWT_BEARER_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"
        
        if grant_type != JWT_BEARER_GRANT_TYPE:
            return self._error_response(
                _("Only the JWT bearer grant type is supported."), 
                400
            )
        
        assertion = data.get("assertion")
        if not assertion:
            return self._error_response(
                _("The \"assertion\" field is required."), 
                400
            )
        
        try:
            account, claims = self._validate_service_account_assertion(assertion)
            token_data = self._generate_service_account_token(account, claims)
            
            self._log_action("service_account_token_issued", {
                "account": account.name,
                "scopes": claims.get("scope", [])
            })
            
            return self._success_response(token_data)
            
        except ServiceAccountJWTError as exc:
            current_app.logger.info(
                "Service account assertion validation failed.",
                extra={"event": "service_account.token.failed", "error": exc.message}
            )
            return self._error_response(exc.message, 403)
        except Exception as e:
            self._log_action("service_account_token_error", {"error": str(e)})
            return self._error_response(_("Token generation failed"), 500)
    
    def _handle_login(self, data: dict) -> dict:
        """ユーザーログイン処理."""
        username = data.get("username")
        password = data.get("password") 
        totp_code = data.get("totp_code")
        scope = data.get("scope", [])
        
        self._log_action("login_attempt", {"username": username})
        
        # ユーザー認証
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return self._error_response(_("Invalid credentials"), 401)
        
        # TOTP検証（有効な場合）
        if user.totp_secret and not verify_totp(user.totp_secret, totp_code):
            return self._error_response(_("Invalid TOTP code"), 401)
        
        # ログイン実行
        login_user(user, remember=True)
        
        # トークン生成
        token_service = TokenService()
        tokens = token_service.generate_tokens(user, scope)
        
        # GUI アクセスクッキー処理
        response_data = self._success_response({
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expires_in": tokens["expires_in"],
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "roles": [role.name for role in user.roles]
            }
        })
        
        if should_issue_gui_access_cookie(scope):
            session[API_LOGIN_SCOPE_SESSION_KEY] = scope
            # Note: GUI クッキーは実際のレスポンス生成時に設定
        
        self._log_action("login_success", {"user_id": user.id})
        return response_data
    
    def _handle_logout(self) -> dict:
        """ログアウト処理."""
        user_id = current_user.id if current_user.is_authenticated else None
        
        logout_user()
        clear_gui_access_cookie()
        
        if API_LOGIN_SCOPE_SESSION_KEY in session:
            del session[API_LOGIN_SCOPE_SESSION_KEY]
        
        self._log_action("logout", {"user_id": user_id})
        return self._success_response(message=_("Logged out successfully"))
    
    def _handle_refresh(self, data: dict) -> dict:
        """トークンリフレッシュ処理."""
        refresh_token = data.get("refresh_token")
        if not refresh_token:
            return self._error_response(_("Refresh token required"), 400)
        
        try:
            token_service = TokenService()
            new_tokens = token_service.refresh_tokens(refresh_token)
            
            self._log_action("token_refresh", {"user_id": new_tokens.get("user_id")})
            return self._success_response(new_tokens)
            
        except Exception as e:
            self._log_action("token_refresh_error", {"error": str(e)})
            return self._error_response(_("Token refresh failed"), 401)
    
    def _handle_auth_check(self) -> dict:
        """認証状態確認."""
        if not current_user.is_authenticated:
            return self._error_response(_("Not authenticated"), 401)
        
        return self._success_response({
            "authenticated": True,
            "user": {
                "id": current_user.id,
                "username": current_user.username,
                "display_name": current_user.display_name,
                "roles": [role.name for role in current_user.roles]
            }
        })
    
    def _validate_service_account_assertion(self, assertion: str):
        """サービスアカウントアサーション検証."""
        audiences = settings.service_account_signing_audiences
        if not audiences:
            raise ServiceAccountJWTError("audience_not_configured", 
                                       _("Service account signing audience is not configured."))
        
        audience_param = audiences[0] if len(audiences) == 1 else tuple(audiences)
        
        return ServiceAccountTokenValidator.verify(
            assertion,
            audience=audience_param,
            required_scopes=None,
        )
    
    def _generate_service_account_token(self, account, claims: dict) -> dict:
        """サービスアカウントトークン生成."""
        # 基本検証
        if claims.get("iss") != account.name or claims.get("sub") != account.name:
            raise ServiceAccountJWTError("issuer_mismatch",
                                       _("The assertion issuer must match the service account name."))
        
        if "scope" not in claims:
            raise ServiceAccountJWTError("scope_required", 
                                       _("The \"scope\" claim is required."))
        
        # トークン生成
        token_service = TokenService()
        return token_service.generate_service_account_token(account, claims)