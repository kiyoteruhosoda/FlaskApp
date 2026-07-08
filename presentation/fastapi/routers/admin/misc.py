"""管理者ダッシュボード統計 API（FastAPI）。

Flask-Smorest 版 ``presentation/web/api/admin_misc.py`` を移植。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.application.authenticated_principal import AuthenticatedPrincipal
from shared.kernel.database.session import get_db
from presentation.fastapi.dependencies.auth import get_current_principal

router = APIRouter(prefix="/admin", tags=["admin:dashboard"])


def _require_system_settings(principal: AuthenticatedPrincipal) -> None:
    if not principal.can("admin:system-settings"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "forbidden", "message": "admin:system-settings permission required"},
        )


@router.get("/dashboard", response_model=dict)
async def api_admin_dashboard(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """ダッシュボード統計を返す。"""
    from shared.infrastructure.models.user import User, Role
    from shared.infrastructure.models.group import Group
    from shared.infrastructure.models.service_account import ServiceAccount
    from shared.infrastructure.models.job_sync import JobSync

    _require_system_settings(principal)

    stats: dict = {
        "users": {
            "total": db.query(User).count(),
            "active": db.query(User).filter_by(is_active=True).count(),
        },
        "roles": db.query(Role).count(),
        "groups": db.query(Group).count(),
        "serviceAccounts": db.query(ServiceAccount).count(),
    }

    try:
        from bounded_contexts.photonest.infrastructure.photo_models import Media, Album, Tag

        stats["media"] = {
            "total": db.query(Media).count(),
            "photos": db.query(Media).filter_by(is_video=False).count(),
            "videos": db.query(Media).filter_by(is_video=True).count(),
        }
        stats["albums"] = db.query(Album).count()
        stats["tags"] = db.query(Tag).count()
    except Exception:
        pass

    try:
        recent_jobs = (
            db.query(JobSync).order_by(JobSync.id.desc()).limit(5).all()
        )
        stats["recentJobs"] = [
            {
                "id": j.id,
                "target": j.target,
                "status": j.status,
                "startedAt": (
                    j.started_at.isoformat().replace("+00:00", "Z")
                    if j.started_at
                    else None
                ),
            }
            for j in recent_jobs
        ]
    except Exception:
        stats["recentJobs"] = []

    return {"stats": stats}
