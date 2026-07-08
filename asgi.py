"""ASGI エントリポイント。

FastAPI が全リクエストを処理する。React SPA は FastAPI の StaticFiles
と ``presentation/fastapi/routers/spa.py`` の catch-all ルートで配信する。

起動方法::

    uvicorn asgi:app --host 0.0.0.0 --port 8000

"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from presentation.fastapi.app import create_app as create_fastapi_app

# FastAPI アプリ（ASGI）
app = create_fastapi_app()
