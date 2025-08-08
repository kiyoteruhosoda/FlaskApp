import os
from dotenv import load_dotenv

# .env読み込み（Flask起動前に必ず実行）
load_dotenv()

class Config:
    SECRET_KEY = os.environ["SECRET_KEY"]  # 必須
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 必須（環境変数から取得）
    SQLALCHEMY_DATABASE_URI = os.environ["DATABASE_URI"]

    # 任意（存在する場合のみ設定）
    SQLALCHEMY_BINDS = {}
    feature_x_uri = os.environ.get("FEATURE_X_DB_URI")
    if feature_x_uri:
        SQLALCHEMY_BINDS["feature_x"] = feature_x_uri

    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 1800,
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "connect_args": {
            "connect_timeout": 10
        },
    }
