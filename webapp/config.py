import json
import os
import sys
from types import ModuleType

from dotenv import load_dotenv

from core.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS

load_dotenv()


_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _coerce_env_value(name: str, raw: str):
    default = DEFAULT_APPLICATION_SETTINGS.get(name)

    if isinstance(default, bool):
        return raw.lower() in _TRUTHY_VALUES
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(raw)
        except ValueError:
            return default
    if isinstance(default, float):
        try:
            return float(raw)
        except ValueError:
            return default
    if isinstance(default, (list, dict)):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    return raw


def _setting(name: str, *, env_name: str | None = None):
    env_key = env_name or name
    if env_key:
        raw = os.environ.get(env_key)
        if raw is not None:
            return _coerce_env_value(name, raw)
    return DEFAULT_APPLICATION_SETTINGS.get(name)


class Config:
    """Base configuration populated from persisted system settings."""

    SECRET_KEY = _setting("SECRET_KEY")
    JWT_SECRET_KEY = _setting("JWT_SECRET_KEY")
    ACCESS_TOKEN_ISSUER = _setting("ACCESS_TOKEN_ISSUER")
    ACCESS_TOKEN_AUDIENCE = _setting("ACCESS_TOKEN_AUDIENCE")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    db_uri = os.environ.get("DATABASE_URI", "sqlite://")
    SQLALCHEMY_DATABASE_URI = db_uri

    # Session settings
    PERMANENT_SESSION_LIFETIME = _setting("PERMANENT_SESSION_LIFETIME")
    SESSION_COOKIE_SECURE = _setting("SESSION_COOKIE_SECURE")
    SESSION_COOKIE_HTTPONLY = _setting("SESSION_COOKIE_HTTPONLY")
    SESSION_COOKIE_SAMESITE = _setting("SESSION_COOKIE_SAMESITE")

    # URL generation and external services
    PREFERRED_URL_SCHEME = _setting("PREFERRED_URL_SCHEME")
    CERTS_API_TIMEOUT = _setting("CERTS_API_TIMEOUT")

    SQLALCHEMY_BINDS = {}
    dashboard_db = _setting("DASHBOARD_DB_URI")
    if dashboard_db:
        SQLALCHEMY_BINDS["dashboard"] = dashboard_db

    # Internationalisation
    LANGUAGES = list(_setting("LANGUAGES") or ["ja", "en"])
    BABEL_TRANSLATION_DIRECTORIES = os.path.join(
        os.path.dirname(__file__), "translations"
    )
    BABEL_DEFAULT_LOCALE = _setting("BABEL_DEFAULT_LOCALE")
    BABEL_DEFAULT_TIMEZONE = _setting("BABEL_DEFAULT_TIMEZONE")

    # Database stability
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 1800,
        "pool_pre_ping": True,
    }

    if not db_uri.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS.update({
            "pool_size": 10,
            "max_overflow": 20,
        })
        if db_uri.startswith("mysql"):
            SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {"connect_timeout": 10}

    # Google OAuth
    GOOGLE_CLIENT_ID = _setting("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = _setting("GOOGLE_CLIENT_SECRET")

    # Encryption for OAuth tokens
    OAUTH_TOKEN_KEY = _setting("OAUTH_TOKEN_KEY")
    OAUTH_TOKEN_KEY_FILE = _setting("OAUTH_TOKEN_KEY_FILE")

    # Download URL signing
    FPV_DL_SIGN_KEY = _setting("FPV_DL_SIGN_KEY")
    FPV_URL_TTL_THUMB = _setting("FPV_URL_TTL_THUMB")
    FPV_URL_TTL_PLAYBACK = _setting("FPV_URL_TTL_PLAYBACK")
    FPV_URL_TTL_ORIGINAL = _setting("FPV_URL_TTL_ORIGINAL")
    UPLOAD_TMP_DIR = _setting("UPLOAD_TMP_DIR")
    UPLOAD_DESTINATION_DIR = _setting("UPLOAD_DESTINATION_DIR")
    UPLOAD_MAX_SIZE = _setting("UPLOAD_MAX_SIZE")
    WIKI_UPLOAD_DIR = _setting("WIKI_UPLOAD_DIR")
    FPV_NAS_THUMBS_DIR = _setting("FPV_NAS_THUMBS_DIR")
    FPV_NAS_PLAY_DIR = _setting("FPV_NAS_PLAY_DIR")
    FPV_ACCEL_THUMBS_LOCATION = _setting("FPV_ACCEL_THUMBS_LOCATION")
    FPV_ACCEL_PLAYBACK_LOCATION = _setting("FPV_ACCEL_PLAYBACK_LOCATION")
    FPV_ACCEL_ORIGINALS_LOCATION = _setting("FPV_ACCEL_ORIGINALS_LOCATION")
    FPV_ACCEL_REDIRECT_ENABLED = _setting("FPV_ACCEL_REDIRECT_ENABLED")

    # Local import settings
    LOCAL_IMPORT_DIR = _setting("LOCAL_IMPORT_DIR")
    FPV_NAS_ORIGINALS_DIR = _setting("FPV_NAS_ORIGINALS_DIR")

    # Celery settings
    broker_url = _setting("CELERY_BROKER_URL")
    result_backend = _setting("CELERY_RESULT_BACKEND")
    task_serializer = "json"
    result_serializer = "json"
    accept_content = ["json"]
    timezone = "UTC"
    enable_utc = True

    CORS_ALLOWED_ORIGINS: tuple[str, ...] = ()


class TestConfig(Config):
    """テスト用の設定クラス"""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}

    SECRET_KEY = "test-secret-key"
    JWT_SECRET_KEY = "test-jwt-secret"
    GOOGLE_CLIENT_ID = ""
    GOOGLE_CLIENT_SECRET = ""
    SESSION_COOKIE_SECURE = False
    SQLALCHEMY_BINDS = {}
    UPLOAD_TMP_DIR = "/tmp/test_upload/tmp"
    UPLOAD_DESTINATION_DIR = "/tmp/test_upload/dest"
    WIKI_UPLOAD_DIR = "/tmp/test_upload/wiki"


class _ReloadSafeModule(ModuleType):
    """Module wrapper that repopulates ``sys.modules`` on attribute access."""

    def __getattribute__(self, name):  # type: ignore[override]
        module_name = super().__getattribute__("__name__")
        current = sys.modules.get(module_name)
        if current is not self:
            sys.modules[module_name] = self
        return super().__getattribute__(name)


_self = sys.modules.get(__name__)
if _self is not None and not isinstance(_self, _ReloadSafeModule):
    _proxy = _ReloadSafeModule(__name__)
    _proxy.__dict__.update(_self.__dict__)
    sys.modules[__name__] = _proxy
