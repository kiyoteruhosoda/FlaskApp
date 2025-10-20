"""Default payloads for persisted system configuration."""
from __future__ import annotations

DEFAULT_APPLICATION_SETTINGS: dict[str, object] = {
    "SECRET_KEY": "dev-secret-key",
    "JWT_SECRET_KEY": "dev-jwt-secret",
    "ACCESS_TOKEN_ISSUER": "fpv-webapp",
    "ACCESS_TOKEN_AUDIENCE": "fpv-webapp",
    "SESSION_COOKIE_SECURE": False,
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SAMESITE": "Lax",
    "PERMANENT_SESSION_LIFETIME": 1800,
    "PREFERRED_URL_SCHEME": "http",
    "CERTS_API_TIMEOUT": 10.0,
    "LANGUAGES": ["en", "ja"],
    "BABEL_DEFAULT_LOCALE": "en",
    "BABEL_DEFAULT_TIMEZONE": "Asia/Tokyo",
    "GOOGLE_CLIENT_ID": "",
    "GOOGLE_CLIENT_SECRET": "",
    "OAUTH_TOKEN_KEY": None,
    "OAUTH_TOKEN_KEY_FILE": None,
    "FPV_DL_SIGN_KEY": "",
    "FPV_URL_TTL_THUMB": 600,
    "FPV_URL_TTL_PLAYBACK": 600,
    "FPV_URL_TTL_ORIGINAL": 600,
    "UPLOAD_TMP_DIR": "/app/data/tmp/upload",
    "UPLOAD_DESTINATION_DIR": "/app/data/uploads",
    "UPLOAD_MAX_SIZE": 100 * 1024 * 1024,
    "WIKI_UPLOAD_DIR": "/app/data/wiki",
    "FPV_NAS_THUMBS_DIR": "",
    "FPV_NAS_PLAY_DIR": "",
    "FPV_ACCEL_THUMBS_LOCATION": "",
    "FPV_ACCEL_PLAYBACK_LOCATION": "",
    "FPV_ACCEL_ORIGINALS_LOCATION": "",
    "FPV_ACCEL_REDIRECT_ENABLED": True,
    "LOCAL_IMPORT_DIR": "/mnt/nas/import",
    "FPV_NAS_ORIGINALS_DIR": "/mnt/nas/photos/originals",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SERVICE_ACCOUNT_SIGNING_AUDIENCE": "",
    "TRANSCODE_CRF": 20,
}

DEFAULT_CORS_SETTINGS: dict[str, object] = {
    "allowedOrigins": [],
}

__all__ = [
    "DEFAULT_APPLICATION_SETTINGS",
    "DEFAULT_CORS_SETTINGS",
]
