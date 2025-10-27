import os
import sys
from types import ModuleType

from sqlalchemy.pool import StaticPool

from dotenv import load_dotenv

from core.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS

load_dotenv()


def _default(name: str):
    return DEFAULT_APPLICATION_SETTINGS.get(name)


class BaseApplicationSettings:
    """Base Flask application configuration populated from persisted system settings."""

    SECRET_KEY = _default("SECRET_KEY")
    JWT_SECRET_KEY = _default("JWT_SECRET_KEY")
    ACCESS_TOKEN_ISSUER = _default("ACCESS_TOKEN_ISSUER")
    ACCESS_TOKEN_AUDIENCE = _default("ACCESS_TOKEN_AUDIENCE")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    db_uri = os.environ.get("DATABASE_URI", "sqlite://")
    SQLALCHEMY_DATABASE_URI = db_uri

    # Session settings
    PERMANENT_SESSION_LIFETIME = _default("PERMANENT_SESSION_LIFETIME")
    SESSION_COOKIE_SECURE = _default("SESSION_COOKIE_SECURE")
    SESSION_COOKIE_HTTPONLY = _default("SESSION_COOKIE_HTTPONLY")
    SESSION_COOKIE_SAMESITE = _default("SESSION_COOKIE_SAMESITE")

    # URL generation and external services
    PREFERRED_URL_SCHEME = _default("PREFERRED_URL_SCHEME")
    CERTS_API_TIMEOUT = _default("CERTS_API_TIMEOUT")

    # Internationalisation
    LANGUAGES = list(_default("LANGUAGES") or ["en", "ja"])
    BABEL_TRANSLATION_DIRECTORIES = os.path.join(
        os.path.dirname(__file__), "translations"
    )
    BABEL_DEFAULT_LOCALE = _default("BABEL_DEFAULT_LOCALE")
    BABEL_DEFAULT_TIMEZONE = _default("BABEL_DEFAULT_TIMEZONE")

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
    GOOGLE_CLIENT_ID = _default("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = _default("GOOGLE_CLIENT_SECRET")

    # Token encryption
    ENCRYPTION_KEY = _default("ENCRYPTION_KEY")
    ENCRYPTION_KEY_FILE = _default("ENCRYPTION_KEY_FILE")

    # Download URL signing
    FPV_DL_SIGN_KEY = _default("FPV_DL_SIGN_KEY")
    FPV_URL_TTL_THUMB = _default("FPV_URL_TTL_THUMB")
    FPV_URL_TTL_PLAYBACK = _default("FPV_URL_TTL_PLAYBACK")
    FPV_URL_TTL_ORIGINAL = _default("FPV_URL_TTL_ORIGINAL")
    UPLOAD_TMP_DIR = _default("UPLOAD_TMP_DIR")
    UPLOAD_DESTINATION_DIR = _default("UPLOAD_DESTINATION_DIR")
    UPLOAD_MAX_SIZE = _default("UPLOAD_MAX_SIZE")
    WIKI_UPLOAD_DIR = _default("WIKI_UPLOAD_DIR")
    FPV_NAS_THUMBS_DIR = _default("FPV_NAS_THUMBS_DIR")
    FPV_NAS_PLAY_DIR = _default("FPV_NAS_PLAY_DIR")
    FPV_ACCEL_THUMBS_LOCATION = _default("FPV_ACCEL_THUMBS_LOCATION")
    FPV_ACCEL_PLAYBACK_LOCATION = _default("FPV_ACCEL_PLAYBACK_LOCATION")
    FPV_ACCEL_ORIGINALS_LOCATION = _default("FPV_ACCEL_ORIGINALS_LOCATION")
    FPV_ACCEL_REDIRECT_ENABLED = _default("FPV_ACCEL_REDIRECT_ENABLED")

    # Local import settings
    LOCAL_IMPORT_DIR = _default("LOCAL_IMPORT_DIR")
    FPV_NAS_ORIGINALS_DIR = _default("FPV_NAS_ORIGINALS_DIR")

    CORS_ALLOWED_ORIGINS: tuple[str, ...] = ()


class TestConfig(BaseApplicationSettings):
    """テスト用の設定クラス"""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }

    SECRET_KEY = "test-secret-key"
    JWT_SECRET_KEY = "test-jwt-secret"
    GOOGLE_CLIENT_ID = ""
    GOOGLE_CLIENT_SECRET = ""
    SESSION_COOKIE_SECURE = False
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
