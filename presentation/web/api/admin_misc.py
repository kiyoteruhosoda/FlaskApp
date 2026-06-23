"""管理 JSON API — ダッシュボード統計・バージョン情報."""
from __future__ import annotations

from flask import jsonify

from shared.infrastructure.models.user import User, Role
from shared.infrastructure.models.group import Group
from shared.infrastructure.models.service_account import ServiceAccount
from bounded_contexts.photonest.infrastructure.photo_models import Media, Album, Tag
from shared.infrastructure.models.job_sync import JobSync
from . import bp
from .routes import login_or_jwt_required, get_current_user


def _require_system_settings():
    user = get_current_user()
    if user is None or not user.can("admin:system-settings"):
        return jsonify({"error": "forbidden", "message": "admin:system-settings permission required"}), 403
    return None


@bp.get("/admin/dashboard")
@login_or_jwt_required
def api_admin_dashboard():
    """ダッシュボード統計を返す。"""
    err = _require_system_settings()
    if err:
        return err

    stats = {
        "users": {
            "total": User.query.count(),
            "active": User.query.filter_by(is_active=True).count(),
        },
        "roles": Role.query.count(),
        "groups": Group.query.count(),
        "serviceAccounts": ServiceAccount.query.count(),
    }

    try:
        stats["media"] = {
            "total": Media.query.count(),
            "photos": Media.query.filter_by(is_video=False).count(),
            "videos": Media.query.filter_by(is_video=True).count(),
        }
        stats["albums"] = Album.query.count()
        stats["tags"] = Tag.query.count()
    except Exception:
        pass

    try:
        recent_jobs = (
            JobSync.query.order_by(JobSync.id.desc()).limit(5).all()
        )
        stats["recentJobs"] = [
            {
                "id": j.id,
                "target": j.target,
                "status": j.status,
                "startedAt": j.started_at.isoformat().replace("+00:00", "Z") if j.started_at else None,
            }
            for j in recent_jobs
        ]
    except Exception:
        stats["recentJobs"] = []

    return jsonify({"stats": stats})
