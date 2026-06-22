"""Shared infrastructure components.

``SqlAlchemyUserRepository`` は遅延公開する。``shared.infrastructure.models.*``
（ORM モデル）を import する際にパッケージ初期化で repository → モデルの循環
import が発生しないようにするため、PEP 562 の ``__getattr__`` で必要時のみ解決する。
"""

__all__ = ["SqlAlchemyUserRepository"]


def __getattr__(name):  # PEP 562: 遅延 import で循環を回避
    if name == "SqlAlchemyUserRepository":
        from .user_repository import SqlAlchemyUserRepository

        return SqlAlchemyUserRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
