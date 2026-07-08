"""サーバーライフサイクルに関するログ出力を提供するユーティリティ（Flask 非依存版）。

Flask 撤廃（T11）に伴い、Flask アプリへの依存を除去した。
FastAPI では lifespan イベントで直接ログを記録する。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_lifecycle_logging(app: object | None = None) -> None:
    """ライフサイクルログの登録（後方互換スタブ）。

    Flask アプリを引数として受け取っても no-op として扱う。
    FastAPI での起動/停止ログは ``presentation/fastapi/app.py`` の lifespan で行う。
    """
    logger.debug("register_lifecycle_logging called (no-op in FastAPI mode)")


