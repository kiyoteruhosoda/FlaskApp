import os
from dotenv import load_dotenv


def _env_as_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

# .envファイルを読み込み
load_dotenv()

class Config:
    # 環境変数にSECRET_KEYが無い場合はデフォルト値を使用
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    db_uri = os.environ.get("DATABASE_URI", "sqlite://")
    SQLALCHEMY_DATABASE_URI = db_uri
    
    # セッション設定
    PERMANENT_SESSION_LIFETIME = 1800  # 30分（秒）
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    
    # URL生成設定
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "http")

    SQLALCHEMY_BINDS = {}
    fx = os.environ.get("FEATURE_X_DB_URI")
    if fx:
        SQLALCHEMY_BINDS["feature_x"] = fx

    # i18n
    LANGUAGES = ["ja", "en"]
    BABEL_TRANSLATION_DIRECTORIES = os.path.join(os.path.dirname(__file__), "translations")
    BABEL_DEFAULT_LOCALE = os.environ.get("BABEL_DEFAULT_LOCALE", "ja")
    BABEL_DEFAULT_TIMEZONE = os.environ.get("BABEL_DEFAULT_TIMEZONE", "Asia/Tokyo")

    # DB安定化
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }

    if db_uri.startswith("sqlite"):
        # SQLiteでは接続プール関連の設定は無効
        pass
    else:
        SQLALCHEMY_ENGINE_OPTIONS.update({
            "pool_size": 10,
            "max_overflow": 20,
        })
        if db_uri.startswith("mysql"):
            SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {"connect_timeout": 10}

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    # Encryption for OAuth tokens
    OAUTH_TOKEN_KEY = os.environ.get("OAUTH_TOKEN_KEY")
    OAUTH_TOKEN_KEY_FILE = os.environ.get("OAUTH_TOKEN_KEY_FILE") or os.environ.get(
        "FPV_OAUTH_TOKEN_KEY_FILE"
    )

    # Download URL signing
    FPV_DL_SIGN_KEY = os.environ.get("FPV_DL_SIGN_KEY", "")
    FPV_URL_TTL_THUMB = int(os.environ.get("FPV_URL_TTL_THUMB", "600"))
    FPV_URL_TTL_PLAYBACK = int(os.environ.get("FPV_URL_TTL_PLAYBACK", "600"))
    FPV_URL_TTL_ORIGINAL = int(os.environ.get("FPV_URL_TTL_ORIGINAL", "600"))
    UPLOAD_TMP_DIR = os.environ.get("UPLOAD_TMP_DIR", "/data/tmp/upload")
    UPLOAD_DESTINATION_DIR = os.environ.get("UPLOAD_DESTINATION_DIR", "/data/uploads")
    UPLOAD_MAX_SIZE = int(os.environ.get("UPLOAD_MAX_SIZE", str(100 * 1024 * 1024)))
    FPV_NAS_THUMBS_DIR = os.environ.get("FPV_NAS_THUMBS_CONTAINER_DIR") or os.environ.get(
        "FPV_NAS_THUMBS_DIR", ""
    )
    FPV_NAS_PLAY_DIR = os.environ.get("FPV_NAS_PLAY_CONTAINER_DIR") or os.environ.get(
        "FPV_NAS_PLAY_DIR", ""
    )
    FPV_ACCEL_THUMBS_LOCATION = os.environ.get("FPV_ACCEL_THUMBS_LOCATION", "")
    FPV_ACCEL_PLAYBACK_LOCATION = os.environ.get("FPV_ACCEL_PLAYBACK_LOCATION", "")
    FPV_ACCEL_ORIGINALS_LOCATION = os.environ.get("FPV_ACCEL_ORIGINALS_LOCATION", "")
    FPV_ACCEL_REDIRECT_ENABLED = _env_as_bool("FPV_ACCEL_REDIRECT_ENABLED", True)
    
    # Local import settings
    LOCAL_IMPORT_DIR = os.environ.get("LOCAL_IMPORT_DIR", "/mnt/nas/import")
    FPV_NAS_ORIGINALS_DIR = os.environ.get("FPV_NAS_ORIGINALS_DIR", "/mnt/nas/photos/originals")

    # Celery settings
    broker_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    result_backend = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    task_serializer = "json"
    result_serializer = "json"
    accept_content = ["json"]
    timezone = "UTC"
    enable_utc = True


class TestConfig(Config):
    """テスト用の設定クラス"""
    TESTING = True
    # SQLiteを強制的に使用（インメモリDBでも可）
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    
    # 必要な最小限の設定
    SECRET_KEY = "test-secret-key"
    JWT_SECRET_KEY = "test-jwt-secret"
    
    # OAuth設定
    GOOGLE_CLIENT_ID = ""
    GOOGLE_CLIENT_SECRET = ""
    
    # Session設定
    SESSION_COOKIE_SECURE = False

    # Feature X DB binding（テスト時は無効）
    SQLALCHEMY_BINDS = {}
    UPLOAD_TMP_DIR = "/tmp/test_upload/tmp"
    UPLOAD_DESTINATION_DIR = "/tmp/test_upload/dest"
