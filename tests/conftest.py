import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))


@pytest.fixture
def app_context():
    """アプリケーションコンテキストを提供するfixture"""
    import os
    import importlib
    
    # テスト用の環境変数を設定
    original_env = {}
    test_env = {
        "DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "FEATURE_X_DB_URI": "",
    }
    
    for key, value in test_env.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value
    
    try:
        # configモジュールをリロード
        import webapp.config as config_module
        importlib.reload(config_module)
        
        from webapp import create_app
        from webapp.config import TestConfig
        from webapp.extensions import db
        
        app = create_app()
        app.config.from_object(TestConfig)
        
        with app.app_context():
            db.create_all()
            yield app
            db.session.remove()
            db.drop_all()
    finally:
        # 環境変数を元に戻す
        for key, original_value in original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value