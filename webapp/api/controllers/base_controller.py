"""Base controller for API endpoints with common functionality."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type

from flask import Blueprint, current_app, g, request, jsonify
from flask_login import current_user
from flask_babel import gettext as _
from marshmallow import Schema, ValidationError

from core.settings import settings
from shared.application.authenticated_principal import AuthenticatedPrincipal


class BaseController(ABC):
    """APIコントローラーの基底クラス（ポリモーフィズム）."""
    
    def __init__(self, blueprint: Blueprint):
        """コントローラー初期化."""
        self.bp = blueprint
        self._register_routes()
    
    @abstractmethod
    def _register_routes(self) -> None:
        """サブクラスでルート登録を実装."""
        pass
    
    @property
    def domain_name(self) -> str:
        """ドメイン名を取得."""
        return self.__class__.__name__.replace("Controller", "").lower()
    
    def _validate_request(self, schema: Type[Schema], data: Optional[Dict] = None) -> Dict[str, Any]:
        """リクエストデータをバリデーション."""
        if data is None:
            data = request.get_json() or {}
        
        try:
            return schema().load(data)
        except ValidationError as e:
            current_app.logger.warning(f"{self.domain_name}コントローラー - バリデーションエラー: {e.messages}")
            raise ValueError(_("Invalid request data: %(errors)s", errors=str(e.messages)))
    
    def _get_authenticated_user(self) -> AuthenticatedPrincipal:
        """認証済みユーザーを取得."""
        if not current_user.is_authenticated:
            raise PermissionError(_("Authentication required"))
        
        return AuthenticatedPrincipal(
            user_id=current_user.id,
            username=current_user.username,
            roles=[role.name for role in current_user.roles]
        )
    
    def _require_permission(self, permission: str) -> None:
        """権限チェック."""
        if not current_user.can(permission):
            raise PermissionError(_("Insufficient permissions: %(perm)s", perm=permission))
    
    def _success_response(self, data: Any = None, message: str = None) -> Dict[str, Any]:
        """成功レスポンス."""
        response = {"success": True}
        if data is not None:
            response["data"] = data
        if message:
            response["message"] = message
        return response
    
    def _error_response(self, error: str, code: int = 400) -> tuple[Dict[str, Any], int]:
        """エラーレスポンス."""
        return {"success": False, "error": error}, code
    
    def _log_action(self, action: str, details: Dict[str, Any] = None) -> None:
        """アクション実行ログ."""
        log_data = {
            "domain": self.domain_name,
            "action": action,
            "user_id": current_user.id if current_user.is_authenticated else None,
            "details": details or {}
        }
        current_app.logger.info(f"{self.domain_name}アクション: {action}", extra=log_data)


class DomainControllerRegistry:
    """ドメインコントローラーの登録管理（Factory Pattern）."""
    
    def __init__(self):
        self._controllers: Dict[str, BaseController] = {}
    
    def register(self, controller: BaseController) -> None:
        """コントローラーを登録."""
        domain = controller.domain_name
        if domain in self._controllers:
            pass  # 重複登録を警告（コンソール出力なし）
        
        self._controllers[domain] = controller
    
    def get_controller(self, domain: str) -> Optional[BaseController]:
        """ドメインコントローラーを取得."""
        return self._controllers.get(domain)
    
    def get_all_controllers(self) -> Dict[str, BaseController]:
        """全コントローラーを取得."""
        return self._controllers.copy()


# グローバルレジストリインスタンス
controller_registry = DomainControllerRegistry()