import os
from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()

class Config:
    SECRET_KEY = os.environ["SECRET_KEY"]
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    db_uri = os.environ.get("DATABASE_URI", "sqlite://")
    SQLALCHEMY_DATABASE_URI = db_uri
    
    # セッション設定
    PERMANENT_SESSION_LIFETIME = 1800  # 30分（秒）
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

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
        "pool_size": 10,
        "max_overflow": 20,
    }

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
    FPV_NAS_THUMBS_DIR = os.environ.get("FPV_NAS_THUMBS_DIR", "")
    FPV_NAS_PLAY_DIR = os.environ.get("FPV_NAS_PLAY_DIR", "")
    
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
