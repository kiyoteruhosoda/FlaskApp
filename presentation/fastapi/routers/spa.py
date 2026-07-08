"""React SPA 配信ルーター（FastAPI）。

Flask の ``presentation/web/routes/react_routes.py`` を置き換える。
フロントエンドビルド成果物（``frontend/build/``）を FastAPI から直接配信する。

- ``/assets/*``         : Vite ビルド成果物（JS/CSS）
- ``/``                 : React SPA の ``index.html``
- ``/<path:path>``      : 全クライアントサイドルートを ``index.html`` にフォールバック
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

# フロントエンドのビルドパス（プロジェクトルートからの相対位置）
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_BUILD_DIR = _PROJECT_ROOT / "frontend" / "build"
_ASSETS_DIR = _BUILD_DIR / "assets"
_INDEX_HTML = _BUILD_DIR / "index.html"

# 非 SPA 静的ファイル（React ルートではなくファイルそのものを返す）
_STATIC_FILES = {"manifest.json", "logo192.png", "robots.txt", "vite.svg", "favicon.ico"}

# /api, /health, /healthz はこのルーターが触らない（FastAPI の上位ルーターが処理）
_EXCLUDED_PREFIXES = ("api/", "health/", "healthz", "assets/")

router = APIRouter(tags=["spa"])


def _serve_index() -> FileResponse | HTMLResponse:
    """React アプリの index.html を返す。ビルドがなければ開発用メッセージを表示。"""
    if _INDEX_HTML.exists():
        return FileResponse(str(_INDEX_HTML), media_type="text/html")

    return HTMLResponse(
        content="""<!DOCTYPE html>
<html>
<head><title>PhotoNest - Development Mode</title></head>
<body>
  <h1>PhotoNest - Development Mode</h1>
  <p>React build not found. Vite dev server を直接利用してください:</p>
  <p><a href="http://localhost:3000">http://localhost:3000</a></p>
  <pre>cd frontend && npm run dev</pre>
  <hr>
  <p>本番用ビルド:</p>
  <pre>cd frontend && npm run build</pre>
</body>
</html>""",
        status_code=200,
    )


@router.get("/", response_model=None)
async def spa_root() -> FileResponse | HTMLResponse:
    """React SPA のルートパスを配信する。"""
    return _serve_index()


@router.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
async def chrome_devtools() -> JSONResponse:
    """Chrome DevTools 向けの空レスポンス。"""
    return JSONResponse(content={}, status_code=204)


@router.get("/{path:path}", include_in_schema=False, response_model=None)
async def spa_catch_all(path: str) -> FileResponse | HTMLResponse | JSONResponse:
    """全クライアントサイドルートを React SPA の index.html にフォールバックする。

    /api, /health, /assets プレフィックスは FastAPI の上位ルーターが先に処理する
    ため、ここには到達しない。
    """
    # 除外プレフィックス（念のため）
    for prefix in _EXCLUDED_PREFIXES:
        if path.startswith(prefix):
            return JSONResponse(content={"error": "not_found"}, status_code=404)

    # 既知の静的ファイル
    if path in _STATIC_FILES:
        static_path = _BUILD_DIR / path
        if static_path.exists():
            return FileResponse(str(static_path))
        return JSONResponse(content={"error": "not_found"}, status_code=404)

    # その他はすべて SPA にフォールバック
    return _serve_index()
