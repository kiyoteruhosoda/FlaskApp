"""リクエスト単位で共有スコープセッションを破棄するミドルウェア（FastAPI）。

Flask-SQLAlchemy 互換の ``db.session`` はスレッドローカルな ``scoped_session``
である。FastAPI の ``async def`` エンドポイントはすべて単一のイベントループ
スレッド上で実行されるため、``db.session`` はプロセス内で 1 つの Session を
共有し続ける。MariaDB/InnoDB の既定分離レベル（REPEATABLE READ）では、この
Session が最初の SELECT でトランザクション（スナップショット）を開始したあと
commit / rollback / remove するまで同じスナップショットを見続ける。

読み取り専用エンドポイント（commit しない）ではスナップショットが固定され、
以降に別コネクション（``get_db``）でコミットされた行が永遠に見えなくなる。
その結果、一覧（``get_db`` 使用）には表示されるのに詳細取得（``db.session``
使用）が ``not_found`` を返す、といった不整合が発生する。

各リクエスト終了時に ``db.session.remove()`` することで、次リクエストの最初の
クエリが新しいスナップショットで開始されるようにする。
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from shared.kernel.database.db import db


class ScopedSessionLifecycleMiddleware(BaseHTTPMiddleware):
    """リクエスト完了時に共有スコープセッションを破棄する。"""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        finally:
            db.session.remove()


__all__ = ["ScopedSessionLifecycleMiddleware"]
