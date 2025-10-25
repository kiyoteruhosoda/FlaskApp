from datetime import datetime

import os

from flask import Blueprint, jsonify, current_app
from sqlalchemy import text

from .extensions import db
from core.time import utc_now_isoformat
from core.settings import settings
from domain.storage import StorageDomain

# 認証なしのhealth用Blueprint
health_bp = Blueprint("health", __name__, url_prefix="/health")


@health_bp.get("/live")
def health_live():
    """Simple liveness probe."""
    return jsonify({"status": "ok"}), 200


@health_bp.get("/ready")
def health_ready():
    """Readiness probe checking database and NAS paths."""
    ok = True
    details = {}

    try:
        db.session.execute(text("SELECT 1"))
        details["db"] = "ok"
    except Exception:
        ok = False
        details["db"] = "error"

    service = settings.storage.service()
    directory_checks = {
        "fpv_nas_thumbs_dir": StorageDomain.MEDIA_THUMBNAILS,
        "fpv_nas_play_dir": StorageDomain.MEDIA_PLAYBACK,
    }
    storage_accessor = settings.storage
    for field, domain in directory_checks.items():
        area = service.for_domain(domain)
        configured = current_app.config.get(area.config_key)
        if configured:
            configured_path = os.fspath(configured)
            if os.path.exists(configured_path):
                details[field] = "ok"
                continue
            ok = False
            details[field] = "missing"
            continue

        fallback_path = storage_accessor.configured(area.config_key)
        if fallback_path:
            fallback_path = os.fspath(fallback_path)
            if os.path.exists(fallback_path):
                details[field] = "ok"
                continue

        base = area.first_existing()
        if base and os.path.exists(base):
            details[field] = "ok"
        else:
            ok = False
            details[field] = "missing"

    redis_url = settings.redis_url
    if redis_url:
        try:  # pragma: no cover - optional dependency
            import redis

            r = redis.from_url(redis_url)
            r.ping()
            details["redis"] = "ok"
        except Exception:
            ok = False
            details["redis"] = "error"

    status = 200 if ok else 503
    details["status"] = "ok" if ok else "error"
    return jsonify(details), status


@health_bp.get("/beat")
def health_beat():
    """Return last beat timestamp and current server time."""
    last = settings.last_beat_at
    return (
        jsonify(
            {
                "lastBeatAt": last.isoformat() if isinstance(last, datetime) else None,
                "server_time": utc_now_isoformat(),
            }
        ),
        200,
    )
