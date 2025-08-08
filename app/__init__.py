import os
from flask import Flask
from dotenv import load_dotenv
from .extensions import db, migrate, login_manager

def create_app():
    # .envを開発時のみロード（本番は環境変数）
    if os.path.exists(".env"):
        load_dotenv()

    app = Flask(__name__)
    app.config.from_object("config.Config")

    # 拡張初期化
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # モデルのimport（Alembicが見つけられるように）
    from .models import user as user_model  # noqa

    # Blueprint登録
    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")

    #from .feature_x import bp as feature_x_bp
    #app.register_blueprint(feature_x_bp, url_prefix="/feature-x")

    return app
