"""API Controllers for domain separation."""

# 先にコントローラーをインポート（循環参照回避）
from .base_controller import BaseController
from .auth_controller import AuthController
# NOTE: 他のコントローラーは依存関係解決後に追加
# from .media_controller import MediaController
# from .album_controller import AlbumController
# from .tag_controller import TagController
# from .google_controller import GoogleController
# from .storage_controller import StorageController

__all__ = [
    "BaseController",
    "AuthController",
    # "MediaController", 
    # "AlbumController",
    # "TagController",
    # "GoogleController",
    # "StorageController",
]