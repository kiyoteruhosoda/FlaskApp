"""テスト専用の設定クラスを提供するモジュール。"""

from sqlalchemy.pool import StaticPool

from webapp.config import BaseApplicationSettings


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
    MEDIA_UPLOAD_TEMP_DIRECTORY = "/tmp/test_upload/tmp"
    MEDIA_UPLOAD_DESTINATION_DIRECTORY = "/tmp/test_upload/dest"
    WIKI_UPLOAD_DIRECTORY = "/tmp/test_upload/wiki"
