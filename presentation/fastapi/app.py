"""FastAPI アプリファクトリ。

``create_app()`` を呼び出すことでルーター群を組み立てた
``fastapi.FastAPI`` インスタンスを返す。
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from shared.kernel.settings.settings import settings
from shared.kernel.version import get_version_string

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """アプリ起動/停止時のライフサイクル処理。"""
    logger.info("FastAPI アプリ起動: version=%s", get_version_string())
    yield
    logger.info("FastAPI アプリ終了")


def create_app() -> FastAPI:
    """FastAPI アプリケーションインスタンスを生成・設定して返す。"""

    app = FastAPI(
        title="nolumia API",
        version=get_version_string(),
        description=(
            "nolumia family photo management API. "
            "FastAPI 移行版（T11）。"
        ),
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    _configure_cors(app)

    # ------------------------------------------------------------------
    # エラーハンドラー
    # ------------------------------------------------------------------
    _register_error_handlers(app)

    # ------------------------------------------------------------------
    # 静的ファイル（React SPA assets）
    # Starlette はルートリストを登録順に評価するため、SPA catch-all
    # （/{path:path}）より先にマウントしないと /assets/* が奪われて 404 になる。
    # ------------------------------------------------------------------
    _mount_static_files(app)

    # ------------------------------------------------------------------
    # ルーター登録
    # ------------------------------------------------------------------
    _register_routers(app)

    return app


def _mount_static_files(app: FastAPI) -> None:
    """フロントエンドビルドの静的ファイルをマウントする。"""
    _project_root = Path(__file__).resolve().parents[2]
    assets_dir = _project_root / "frontend" / "build" / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="react_assets")
    else:
        logger.warning(
            "React build assets directory not found: %s — "
            "フロントエンドのビルドが完了していません。`cd frontend && npm run build` を実行してください。",
            assets_dir,
        )


def _configure_cors(app: FastAPI) -> None:
    """CORS ミドルウェアを設定する。"""
    allowed_origins = settings.cors_allowed_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _register_error_handlers(app: FastAPI) -> None:
    """グローバルエラーハンドラーを登録する。"""

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s %s", request.method, request.url)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_server_error", "message": "An unexpected error occurred."},
        )


def _register_routers(app: FastAPI) -> None:
    """全ルーターを ``/api`` プレフィックスで登録する。"""
    from presentation.fastapi.routers.health import router as health_router
    from presentation.fastapi.routers.auth import router as auth_router, token_router
    from presentation.fastapi.routers.version import router as version_router
    from presentation.fastapi.routers.echo import router as echo_router
    from presentation.fastapi.routers.user_preferences import router as user_prefs_router
    from presentation.fastapi.routers.auth_profile import router as auth_profile_router
    from presentation.fastapi.routers.auth_passkeys import router as auth_passkeys_router
    from presentation.fastapi.routers.totp import router as totp_router
    from presentation.fastapi.routers.sync_jobs import router as sync_jobs_router
    from presentation.fastapi.routers.local_import import router as local_import_router
    from presentation.fastapi.routers.upload import router as upload_router
    from presentation.fastapi.routers.service_account_keys import router as sa_keys_router
    from presentation.fastapi.routers.service_account_signing import router as sa_signing_router
    from presentation.fastapi.routers.maintenance import router as maintenance_router
    from presentation.fastapi.routers.picker_session import router as picker_session_router

    # 管理者ルーター
    from presentation.fastapi.routers.admin.users import router as admin_users_router
    from presentation.fastapi.routers.admin.roles import router as admin_roles_router
    from presentation.fastapi.routers.admin.groups import router as admin_groups_router
    from presentation.fastapi.routers.admin.permissions import router as admin_permissions_router
    from presentation.fastapi.routers.admin.service_accounts import router as admin_sa_router
    from presentation.fastapi.routers.admin.misc import router as admin_misc_router
    from presentation.fastapi.routers.admin.config import router as admin_config_router
    from presentation.fastapi.routers.admin.photo_exports import router as admin_photo_exports_router
    from presentation.fastapi.routers.admin.cdn import router as admin_cdn_router
    from presentation.fastapi.routers.admin.blob import router as admin_blob_router
    from presentation.fastapi.routers.admin.impersonation import router as admin_impersonation_router

    # Phase 3 ルーター
    from presentation.fastapi.routers.google_oauth import (
        router as google_oauth_router,
        callback_router as google_oauth_callback_router,
    )
    from presentation.fastapi.routers.media import router as media_router
    from presentation.fastapi.routers.albums import router as albums_router
    from presentation.fastapi.routers.tags import router as tags_router

    # ヘルスチェック（/api プレフィックスなし）
    app.include_router(health_router)

    # API ルーター（/api プレフィックスあり）
    api_prefix = "/api"
    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(token_router, prefix=api_prefix)
    app.include_router(auth_profile_router, prefix=api_prefix)
    app.include_router(auth_passkeys_router, prefix=api_prefix)
    app.include_router(version_router, prefix=api_prefix)
    app.include_router(echo_router, prefix=api_prefix)
    app.include_router(user_prefs_router, prefix=api_prefix)
    app.include_router(totp_router, prefix=api_prefix)
    app.include_router(sync_jobs_router, prefix=api_prefix)
    app.include_router(local_import_router, prefix=api_prefix)
    app.include_router(upload_router, prefix=api_prefix)
    app.include_router(sa_keys_router, prefix=api_prefix)
    app.include_router(sa_signing_router, prefix=api_prefix)
    app.include_router(maintenance_router, prefix=api_prefix)
    app.include_router(picker_session_router, prefix=api_prefix)

    # Phase 3: メディア / Google OAuth / アルバム / タグ
    app.include_router(google_oauth_router, prefix=api_prefix)
    # Google OAuth コールバックは Google が固定 URL /auth/google/callback へ
    # リダイレクトするため、/api プレフィックスなしで（SPA catch-all より前に）登録する。
    app.include_router(google_oauth_callback_router)
    app.include_router(media_router, prefix=api_prefix)
    app.include_router(albums_router, prefix=api_prefix)
    app.include_router(tags_router, prefix=api_prefix)

    # Wiki（router が /wiki/api プレフィックスを持つためプレフィックスなしで登録）
    from presentation.fastapi.routers.wiki import router as wiki_router
    app.include_router(wiki_router)

    # Certs（/api プレフィックスで登録）
    from presentation.fastapi.routers.certs import router as certs_router
    app.include_router(certs_router, prefix=api_prefix)

    # Local Import Status（/api プレフィックスで登録）
    from presentation.fastapi.routers.local_import_status import router as local_import_status_router
    app.include_router(local_import_status_router, prefix=api_prefix)

    # 管理者 API
    app.include_router(admin_users_router, prefix=api_prefix)
    app.include_router(admin_roles_router, prefix=api_prefix)
    app.include_router(admin_groups_router, prefix=api_prefix)
    app.include_router(admin_permissions_router, prefix=api_prefix)
    app.include_router(admin_sa_router, prefix=api_prefix)
    app.include_router(admin_misc_router, prefix=api_prefix)
    app.include_router(admin_config_router, prefix=api_prefix)
    app.include_router(admin_photo_exports_router, prefix=api_prefix)
    app.include_router(admin_cdn_router, prefix=api_prefix)
    app.include_router(admin_blob_router, prefix=api_prefix)
    app.include_router(admin_impersonation_router, prefix=api_prefix)

    # React SPA サーブ（catch-all — 必ず最後に登録する）
    from presentation.fastapi.routers.spa import router as spa_router
    app.include_router(spa_router)
