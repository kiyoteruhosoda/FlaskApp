"""ASGI エントリポイント。

FastAPI が ``/api/*`` を処理し、Flask が UI ルート（``/auth/*``,
``/dashboard/*`` 等）を処理する Strangler Fig 構成。

起動方法::

    uvicorn asgi:app --host 0.0.0.0 --port 8000

"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from presentation.fastapi.app import create_app as create_fastapi_app

# FastAPI アプリ（ASGI）
app = create_fastapi_app()

# ---------------------------------------------------------------------------
# Flask UI ルートのマウント（Strangler Fig）
#
# ``/api/*`` と ``/healthz``, ``/health/*`` は FastAPI が処理する。
# その他のルート（テンプレート / 管理 UI / Wiki 等）は Flask (WSGI) が処理する。
# Flask WSGI アプリを ``a2wsgi.WSGIMiddleware`` で ASGI に変換してマウントする。
# ---------------------------------------------------------------------------

try:
    from a2wsgi import WSGIMiddleware
    from starlette.routing import Mount
    from starlette.middleware import Middleware

    from presentation.web import create_app as create_flask_app
    from shared.kernel.logging.lifecycle_logging import register_lifecycle_logging

    _flask_wsgi_app = create_flask_app()
    register_lifecycle_logging(_flask_wsgi_app)

    # Flask WSGI を ASGI ミドルウェアとしてラップ
    _flask_asgi = WSGIMiddleware(_flask_wsgi_app)

    # FastAPI の catch-all ルートとして Flask を追加する
    # （FastAPI のルートにマッチしないパスは Flask へ流れる）
    from starlette.routing import Route
    from starlette.responses import Response

    async def _flask_passthrough(scope, receive, send):
        await _flask_asgi(scope, receive, send)

    # FastAPI の router に catch-all を追加
    from fastapi.routing import APIRoute
    from starlette.routing import BaseRoute

    # Flask を catch-all ミドルウェアとして追加
    app.add_route(
        "/{path:path}",
        _flask_passthrough,
        include_in_schema=False,
    )

except ImportError:
    import logging
    logging.getLogger(__name__).warning(
        "a2wsgi がインストールされていないため Flask UI ルートは利用できません。"
        "`pip install a2wsgi` でインストールしてください。"
    )
except Exception as exc:
    import logging
    logging.getLogger(__name__).error("Flask アプリのマウントに失敗しました: %s", exc)
