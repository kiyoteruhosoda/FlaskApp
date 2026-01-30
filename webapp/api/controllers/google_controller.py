"""Google Photos integration domain controller."""

from typing import Dict, Any

from flask import Blueprint, current_app, request, session, redirect, url_for
from flask_login import login_required, current_user
from flask_babel import gettext as _

from .base_controller import BaseController
from core.models.google_account import GoogleAccount
from webapp.auth.utils import refresh_google_token, RefreshTokenError
from core.crypto import decrypt


class GoogleController(BaseController):
    """Google Photos統合ドメインコントローラー."""
    
    def _register_routes(self) -> None:
        """Google関連のルートを登録."""
        
        @self.bp.get("/google/accounts")
        @login_required
        def list_google_accounts():
            """Googleアカウント一覧."""
            return self._handle_google_accounts_list()
        
        @self.bp.patch("/google/accounts/<int:account_id>")
        @login_required
        def update_google_account(account_id: int):
            """Googleアカウント更新."""
            return self._handle_google_account_update(account_id)
        
        @self.bp.delete("/google/accounts/<int:account_id>")
        @login_required
        def delete_google_account(account_id: int):
            """Googleアカウント削除."""
            return self._handle_google_account_delete(account_id)
        
        @self.bp.post("/google/accounts/<int:account_id>/test")
        @login_required
        def test_google_account(account_id: int):
            """Googleアカウントテスト."""
            return self._handle_google_account_test(account_id)
        
        @self.bp.post("/google/oauth/start")
        @login_required
        def start_oauth():
            """Google OAuth開始."""
            return self._handle_oauth_start()
    
    def _handle_google_accounts_list(self) -> Dict[str, Any]:
        """Googleアカウント一覧処理."""
        self._require_permission("admin")
        self._log_action("google_accounts_list")
        
        accounts = GoogleAccount.query.all()
        
        accounts_data = []
        for account in accounts:
            accounts_data.append({
                "id": account.id,
                "email": account.email,
                "name": account.name,
                "created_at": account.created_at,
                "last_used": account.last_used,
                "is_active": account.is_active
            })
        
        return self._success_response(accounts_data)
    
    def _handle_google_account_update(self, account_id: int) -> Dict[str, Any]:
        """Googleアカウント更新処理."""
        self._require_permission("admin")
        
        account = GoogleAccount.query.get(account_id)
        if not account:
            return self._error_response(_("Google account not found"), 404)
        
        data = request.get_json() or {}
        
        if "is_active" in data:
            account.is_active = bool(data["is_active"])
            
            from webapp.extensions import db
            db.session.commit()
            
            self._log_action("google_account_updated", {
                "account_id": account_id,
                "is_active": account.is_active
            })
        
        return self._success_response({
            "id": account.id,
            "email": account.email,
            "name": account.name,
            "is_active": account.is_active
        })
    
    def _handle_google_account_delete(self, account_id: int) -> Dict[str, Any]:
        """Googleアカウント削除処理."""
        self._require_permission("admin")
        
        account = GoogleAccount.query.get(account_id)
        if not account:
            return self._error_response(_("Google account not found"), 404)
        
        from webapp.extensions import db
        db.session.delete(account)
        db.session.commit()
        
        self._log_action("google_account_deleted", {
            "account_id": account_id,
            "email": account.email
        })
        
        return self._success_response(message=_("Google account deleted successfully"))
    
    def _handle_google_account_test(self, account_id: int) -> Dict[str, Any]:
        """Googleアカウントテスト処理."""
        self._require_permission("admin")
        
        account = GoogleAccount.query.get(account_id)
        if not account:
            return self._error_response(_("Google account not found"), 404)
        
        try:
            # トークンの有効性テスト
            refresh_google_token(account)
            
            self._log_action("google_account_test_success", {
                "account_id": account_id
            })
            
            return self._success_response({
                "status": "success",
                "message": _("Google account connection is working")
            })
            
        except RefreshTokenError as e:
            self._log_action("google_account_test_failed", {
                "account_id": account_id,
                "error": str(e)
            })
            
            return self._error_response(
                _("Google account connection failed: %(error)s", error=str(e)),
                400
            )
        except Exception as e:
            current_app.logger.error(f"Google account test error: {e}")
            
            return self._error_response(
                _("Google account test failed"),
                500
            )
    
    def _handle_oauth_start(self) -> Dict[str, Any]:
        """Google OAuth開始処理."""
        self._require_permission("admin")
        
        # OAuth URLの生成とリダイレクト
        # 実際の実装では、Google OAuth2フローを開始
        
        oauth_url = self._generate_oauth_url()
        
        self._log_action("oauth_start", {"user_id": current_user.id})
        
        return self._success_response({
            "oauth_url": oauth_url,
            "message": _("Please complete OAuth flow")
        })
    
    def _generate_oauth_url(self) -> str:
        """OAuth URL生成."""
        # Google OAuth2 URLの生成ロジック
        # 実装は既存のOAuth処理を参照
        from urllib.parse import urlencode
        import secrets
        
        state = secrets.token_urlsafe(32)
        session["oauth_state"] = state
        
        base_url = "https://accounts.google.com/o/oauth2/v2/auth"
        params = {
            "client_id": current_app.config.get("GOOGLE_CLIENT_ID"),
            "redirect_uri": url_for("auth.google_callback", _external=True),
            "scope": "openid email profile https://www.googleapis.com/auth/photoslibrary.readonly",
            "response_type": "code",
            "state": state,
            "access_type": "offline",
            "prompt": "consent"
        }
        
        return f"{base_url}?{urlencode(params)}"