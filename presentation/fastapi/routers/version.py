"""バージョン情報 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/version.py`` を移植。
"""
from __future__ import annotations

from fastapi import APIRouter
from shared.kernel.version import get_version_info, get_version_string

router = APIRouter(tags=["system"])


@router.get("/version")
async def version():
    """バージョン情報を返す。"""
    try:
        version_info = get_version_info()
        return {
            "ok": True,
            "version": get_version_string(),
            "details": version_info,
        }
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": "version_unavailable", "version": "unknown"},
        )
