import os
from dotenv import load_dotenv
from celery import Celery
from flask import Flask
from webapp.config import Config
from datetime import timedelta

# .envファイルを読み込み
load_dotenv()

# Flask app factory
def create_app():
    """Create and configure Flask app for Celery."""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize database
    from core.db import db
    db.init_app(app)
    
    # Initialize other extensions  
    from webapp.extensions import migrate, login_manager, babel
    migrate.init_app(app, db)
    login_manager.init_app(app)
    babel.init_app(app)
    
    return app

# Create Celery instance
celery = Celery(
    'cli.src.celery.celery_app',
    broker=os.environ.get("CELERY_BROKER_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0")),
    backend=os.environ.get("CELERY_RESULT_BACKEND", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
)

# Configure Celery
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Tokyo',
    enable_utc=True,
)

# Create Flask app context for Celery tasks
flask_app = create_app()

class ContextTask(celery.Task):
    """Make celery tasks work with Flask app context."""
    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return self.run(*args, **kwargs)

celery.Task = ContextTask

# Import tasks to register them
from cli.src.celery import tasks

# Beat schedule
celery.conf.beat_schedule = {
    "picker-import-watchdog": {
        "task": "picker_import.watchdog",
        "schedule": timedelta(minutes=1),
    },
    "session-recovery": {
        "task": "session_recovery.cleanup_stale_sessions",
        "schedule": timedelta(minutes=5),  # 5分毎に実行
    },
    "backup-cleanup": {
        "task": "backup_cleanup.cleanup",
        "schedule": timedelta(days=1),  # 毎日実行
        "kwargs": {"retention_days": 30},  # 30日より古いファイルを削除
    },
}
