"""後方互換シム: 実体は :mod:`shared.kernel.database.db` へ移動した。

DDD のカーネル層 (Shared Kernel) を単一の真実の源とするため、ORM 用の
共有 SQLAlchemy インスタンスは ``shared.kernel.database.db`` で定義する。
既存の ``from core.db import db`` を壊さないよう同一オブジェクトを再公開する。
"""

from shared.kernel.database.db import db

__all__ = ["db"]
