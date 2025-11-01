"""Default payloads for persisted system configuration."""
from __future__ import annotations

DEFAULT_APPLICATION_SETTINGS: dict[str, object] = {
    "SECRET_KEY": "default-secret-key",
    "JWT_SECRET_KEY": "default-jwt-secret",
    "ACCESS_TOKEN_ISSUER": "fpv-webapp",
    "ACCESS_TOKEN_AUDIENCE": "fpv-webapp",
    "SESSION_COOKIE_SECURE": False,
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SAMESITE": "Lax",
    "PERMANENT_SESSION_LIFETIME": 1800,
    "PREFERRED_URL_SCHEME": "",
    "CERTS_API_TIMEOUT": 10.0,
    "LANGUAGES": ["ja", "en"],
    "BABEL_DEFAULT_LOCALE": "en",
    "BABEL_DEFAULT_TIMEZONE": "Asia/Tokyo",
    "GOOGLE_CLIENT_ID": "",
    "GOOGLE_CLIENT_SECRET": "",
    "ENCRYPTION_KEY": None,
    "MEDIA_DOWNLOAD_SIGNING_KEY": "",
    "MEDIA_THUMBNAIL_URL_TTL_SECONDS": 600,
    "MEDIA_PLAYBACK_URL_TTL_SECONDS": 600,
    "MEDIA_ORIGINAL_URL_TTL_SECONDS": 600,
    "MEDIA_TEMP_DIRECTORY": "/tmp/fpv_tmp",
    "MEDIA_UPLOAD_TEMP_DIRECTORY": "/app/data/tmp/upload",
    "MEDIA_UPLOAD_DESTINATION_DIRECTORY": "/app/data/uploads",
    "MEDIA_UPLOAD_MAX_SIZE_BYTES": 100 * 1024 * 1024,
    "MEDIA_LOCAL_IMPORT_DIRECTORY": "/app/data/media/local_import",
    "MEDIA_THUMBNAILS_DIRECTORY": "/app/data/media/thumbs",
    "MEDIA_PLAYBACK_DIRECTORY": "/app/data/media/playback",
    "MEDIA_ORIGINALS_DIRECTORY": "/app/data/media/originals",
    # X-Accel-Redirect を使用しない構成をデフォルトとし、明示的な有効化のみ許可する
    "MEDIA_ACCEL_REDIRECT_ENABLED": False,
    "MEDIA_ACCEL_THUMBNAILS_LOCATION": "/media/thumbs",
    "MEDIA_ACCEL_PLAYBACK_LOCATION": "/media/playback",
    "MEDIA_ACCEL_ORIGINALS_LOCATION": "/media/originals",
    "SYSTEM_BACKUP_DIRECTORY": "/app/data/backups",
    "WIKI_UPLOAD_DIRECTORY": "/app/data/wiki",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SERVICE_ACCOUNT_SIGNING_AUDIENCE": "",
    "TRANSCODE_CRF": 20,
    "WEBAUTHN_RP_ID": "localhost",
    "WEBAUTHN_ORIGIN": "http://localhost:5000",
    "WEBAUTHN_RP_NAME": "Nolumia",
}

DEFAULT_CORS_SETTINGS: dict[str, object] = {
    "allowedOrigins": [],
}

__all__ = [
    "DEFAULT_APPLICATION_SETTINGS",
    "DEFAULT_CORS_SETTINGS",
]
