# authz.py
"""認可デコレーター（Flask 非依存版）。

Flask 撤廃（T11）に伴い、Flask-Login と flask.abort への依存を除去した。
FastAPI ルートでは ``presentation.fastapi.dependencies.auth.require_permission``
を使用すること。このモジュールは後方互換のためのスタブとして残す。
"""
from __future__ import annotations

import logging
from functools import wraps

logger = logging.getLogger(__name__)


def require_perms(*perm_codes: str):
    """Flask 非依存の認可デコレーター（スタブ）。

    FastAPI への移行が完了しているため、このデコレーターは使用しないこと。
    FastAPI ルートでは ``require_permission`` を ``Depends()`` で使用する。
    """
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            logger.warning(
                "require_perms デコレーターは Flask 撤廃後のスタブです。"
                "FastAPI ルートでは require_permission を使用してください。"
            )
            return fn(*a, **kw)
        return wrapper
    return deco

