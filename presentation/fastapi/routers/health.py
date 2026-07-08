"""ヘルスチェックエンドポイント。

``/healthz``, ``/health/live``, ``/health/ready``, ``/health/beat``
"""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import text

from shared.kernel.database.session import get_db
from shared.kernel.time.clock import utc_now_isoformat
from shared.kernel.settings.settings import settings
from shared.kernel.version import get_version_info, get_version_string

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz():
    """バージョン・コミットハッシュ・サーバー時刻(UTC)を返す軽量ヘルスチェック。"""
    info = get_version_info()
    return {
        "status": "ok",
        "version": get_version_string(),
        "commit_hash": info.get("commit_hash", "unknown"),
        "commit_hash_full": info.get("commit_hash_full", "unknown"),
        "branch": info.get("branch", "unknown"),
        "build_date": info.get("build_date", "unknown"),
        "server_time": utc_now_isoformat(),
    }


@router.get("/health/live")
async def health_live():
    """Kubernetes Liveness プローブ。"""
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready():
    """DB・ストレージ・Redis の疎通を確認する Readiness プローブ。"""
    from bounded_contexts.storage import StorageDomain
    from bounded_contexts.storage.application.filesystem_factory import get_storage_service

    ok = True
    details: dict = {}

    # DB チェック
    try:
        factory = None
        from shared.kernel.database.session import _get_session_factory
        factory = _get_session_factory()
        with factory() as db:
            db.execute(text("SELECT 1"))
        details["db"] = "ok"
    except Exception:
        ok = False
        details["db"] = "error"

    # ストレージチェック
    service = get_storage_service(settings)
    directory_checks = {
        "media_nas_thumbnails_directory": StorageDomain.MEDIA_THUMBNAILS,
        "media_nas_playback_directory": StorageDomain.MEDIA_PLAYBACK,
    }
    for field, domain in directory_checks.items():
        area = service.for_domain(domain)
        base = area.first_existing()
        if base and os.path.exists(base):
            details[field] = "ok"
        else:
            ok = False
            details[field] = "missing"

    # Redis チェック
    redis_url = settings.redis_url
    if redis_url:
        try:
            import redis as redis_lib
            r = redis_lib.from_url(redis_url)
            r.ping()
            details["redis"] = "ok"
        except Exception:
            ok = False
            details["redis"] = "error"

    details["status"] = "ok" if ok else "error"
    from fastapi.responses import JSONResponse
    return JSONResponse(content=details, status_code=200 if ok else 503)


@router.get("/health/beat")
async def health_beat():
    """最後の Celery Beat タイムスタンプとサーバー時刻を返す。"""
    last = settings.last_beat_at
    return {
        "lastBeatAt": last.isoformat() if isinstance(last, datetime) else None,
        "server_time": utc_now_isoformat(),
    }
