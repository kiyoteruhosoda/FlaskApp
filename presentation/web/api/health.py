from datetime import datetime
from functools import wraps
import os

from flask import jsonify, request, current_app
from sqlalchemy import text

from . import bp
from ..bootstrap.extensions import db
from shared.kernel.time.clock import utc_now_isoformat
from shared.kernel.settings.settings import settings
from shared.kernel.version import get_version_info, get_version_string
from bounded_contexts.storage import StorageDomain
from bounded_contexts.storage.application.filesystem_factory import get_storage_service


def skip_auth(f):
    """Skip authentication for this endpoint"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    decorated_function._skip_auth = True
    return decorated_function


@bp.get("/healthz")
@skip_auth
def healthz():
    """バージョン・コミットハッシュ・サーバー時刻(UTC)を返す軽量ヘルスチェック。

    ``/health/*`` 配下のチェック（DB・NAS・Redis 疎通）とは異なり、デプロイ後に
    「どのビルドが動いているか」を即座に確認するためのエンドポイント。
    """
    info = get_version_info()
    return (
        jsonify(
            {
                "status": "ok",
                "version": get_version_string(),
                "commit_hash": info.get("commit_hash", "unknown"),
                "commit_hash_full": info.get("commit_hash_full", "unknown"),
                "branch": info.get("branch", "unknown"),
                "build_date": info.get("build_date", "unknown"),
                "server_time": utc_now_isoformat(),
            }
        ),
        200,
    )


@bp.get("/health/live")
@skip_auth
def health_live():
    """Simple liveness probe."""
    return jsonify({"status": "ok"}), 200


@bp.get("/health/ready")
@skip_auth
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

    service = get_storage_service(settings)
    directory_checks = {
        "media_nas_thumbnails_directory": StorageDomain.MEDIA_THUMBNAILS,
        "media_nas_playback_directory": StorageDomain.MEDIA_PLAYBACK,
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


@bp.get("/health/beat")
@skip_auth
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

