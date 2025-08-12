import os

class Config:
    SECRET_KEY = os.environ["SECRET_KEY"]
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URI"]

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
        "connect_args": {"connect_timeout": 10},
    }

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
