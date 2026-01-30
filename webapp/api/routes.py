"""Refactored API routes using DDD and polymorphism controllers."""

from flask import Blueprint

from .controllers import (
    AuthController,
    # NOTE: 他のコントローラーは依存関係解決後に追加
    # MediaController,
    # AlbumController,
    # TagController,
    # GoogleController,
    # StorageController
)
from .controllers.base_controller import controller_registry

# Blueprint定義
bp = Blueprint("api", __name__, url_prefix="/api")


def register_domain_controllers():
    """ドメインコントローラーを登録."""
    
    # 各ドメインコントローラーを初期化・登録
    controllers = [
        AuthController(bp),
        # 他のコントローラーは段階的に追加
        # MediaController(bp),
        # AlbumController(bp),
        # TagController(bp),
        # GoogleController(bp),
        # StorageController(bp),
    ]
    
    # レジストリに登録
    for controller in controllers:
        controller_registry.register(controller)
    
    return controllers


# コントローラー登録実行（必要時に初期化）
domain_controllers = None

def init_controllers():
    """コントローラーを初期化（遅延ロード）"""
    global domain_controllers
    if domain_controllers is None:
        domain_controllers = register_domain_controllers()
    return domain_controllers


# 既存のスキーマ・ヘルスチェック等のインポートは維持
# from .health import *  # 循環インポートを回避
from .openapi import *
from .pagination import *


# デバッグ・ヘルスチェック用エンドポイント
@bp.get("/health")
def health_check():
    """API ヘルスチェック."""
    return {
        "status": "healthy",
        "version": "2.0",
        "controllers": list(controller_registry.get_all_controllers().keys())
    }


@bp.get("/debug/controllers")
def debug_controllers():
    """登録済みコントローラーのデバッグ情報."""
    controllers_info = {}
    
    for domain, controller in controller_registry.get_all_controllers().items():
        controllers_info[domain] = {
            "class": controller.__class__.__name__,
            "blueprint": controller.bp.name,
            "registered": True
        }
    
    return {
        "registered_controllers": controllers_info,
        "total_count": len(controllers_info)
    }