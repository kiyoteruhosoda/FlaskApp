"""FastAPI プロセスの DB ログ構成。

Flask 版 ``presentation/web/bootstrap/logging_setup.py`` の後継。T11 の
FastAPI 移行時にこの配線が失われ、API プロセスのログが ``log`` テーブル
（System Logs）へ一切保存されなくなっていた。

ルートロガーへ ``DBLogHandler`` を装着することで、ルーターだけでなく
Application 層・Infrastructure 層・shared を含む API プロセス内の
すべてのロガーの出力（INFO 以上）を ``log`` テーブルへ永続化する。
"""
from __future__ import annotations

import logging

from sqlalchemy.engine import make_url

from shared.kernel.logging.db_log_handler import DBLogHandler
from shared.kernel.logging.request_context import RequestIdLogFilter
from shared.kernel.settings.settings import settings

logger = logging.getLogger(__name__)


def _is_in_memory_sqlite(database_uri: str) -> bool:
    try:
        url = make_url(database_uri)
    except Exception:  # pragma: no cover - 不正な URI でロギング構成は止めない
        return False
    return url.get_backend_name() == "sqlite" and url.database in (None, "", ":memory:")


def configure_db_logging() -> None:
    """ルートロガーに DB ログハンドラ（appdb.log）を装着する。

    - テスト実行時（``TESTING``）は装着しない。
    - DB が未設定またはインメモリ SQLite の場合も装着しない。
    - 二重呼び出しではハンドラを重複装着しない。
    """
    if settings.testing:
        return

    database_uri = settings.sqlalchemy_database_uri or settings.database_uri
    if not database_uri or _is_in_memory_sqlite(database_uri):
        return

    root_logger = logging.getLogger()
    if not any(isinstance(h, DBLogHandler) for h in root_logger.handlers):
        handler = DBLogHandler()
        handler.setLevel(logging.INFO)
        handler.addFilter(RequestIdLogFilter())
        root_logger.addHandler(handler)

    # ルートのデフォルト（WARNING）のままだと INFO ログがハンドラへ届かない
    if root_logger.getEffectiveLevel() > logging.INFO:
        root_logger.setLevel(logging.INFO)


__all__ = ["configure_db_logging"]
