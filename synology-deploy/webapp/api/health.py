from datetime import datetime, timezone
from email.utils import formatdate
import os

from flask import current_app, jsonify
from sqlalchemy import text

from . import bp
from ..extensions import db


@bp.get("/health/live")
def health_live():
    """Simple liveness probe."""
    return jsonify({"status": "ok"}), 200


@bp.get("/health/ready")
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

    for key in ("FPV_NAS_THUMBS_DIR", "FPV_NAS_PLAY_DIR"):
        path = current_app.config.get(key)
        field = key.lower()
        if path and os.path.exists(path):
            details[field] = "ok"
        else:
            ok = False
            details[field] = "missing"

    redis_url = current_app.config.get("REDIS_URL")
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


@bp.get("/health/beat")
def health_beat():
    """Return last beat timestamp and current server time."""
    last = current_app.config.get("LAST_BEAT_AT")
    return (
        jsonify(
            {
                "lastBeatAt": last.isoformat() if isinstance(last, datetime) else None,
                "serverTime": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        ),
        200,
    )

