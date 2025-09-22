import os
import logging
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

def setup_celery_logging():
    """Setup logging for Celery workers to use both DBLogHandler and Console output."""
    from core.db_log_handler import DBLogHandler
    import sys
    
    # ログフォーマッター
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    
    # Get Celery logger
    celery_logger = logging.getLogger('celery')
    celery_logger.setLevel(logging.INFO)
    
    # コンソール（Docker）ログハンドラー
    if not any(isinstance(h, logging.StreamHandler) for h in celery_logger.handlers):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        celery_logger.addHandler(console_handler)
    
    # DBログハンドラー
    if not any(isinstance(h, DBLogHandler) for h in celery_logger.handlers):
        db_handler = DBLogHandler(app=flask_app)
        db_handler.setLevel(logging.INFO)
        celery_logger.addHandler(db_handler)
    
    # タスク用のロガー設定
    task_logger = logging.getLogger('celery.task')
    task_logger.setLevel(logging.INFO)
    
    # タスクロガーにもコンソールハンドラーを追加
    if not any(isinstance(h, logging.StreamHandler) for h in task_logger.handlers):
        task_console_handler = logging.StreamHandler(sys.stdout)
        task_console_handler.setLevel(logging.INFO)
        task_console_handler.setFormatter(formatter)
        task_logger.addHandler(task_console_handler)
    
    # タスクロガーにもDBハンドラーを追加
    if not any(isinstance(h, DBLogHandler) for h in task_logger.handlers):
        task_db_handler = DBLogHandler(app=flask_app)
        task_db_handler.setLevel(logging.INFO)
        task_logger.addHandler(task_db_handler)
    
    # picker_import 専用ロガーの設定
    picker_logger = logging.getLogger('picker_import')
    picker_logger.setLevel(logging.INFO)
    
    # picker専用ロガーにもハンドラーを追加
    if not any(isinstance(h, logging.StreamHandler) for h in picker_logger.handlers):
        picker_console_handler = logging.StreamHandler(sys.stdout)
        picker_console_handler.setLevel(logging.INFO)
        picker_console_handler.setFormatter(formatter)
        picker_logger.addHandler(picker_console_handler)
    
    if not any(isinstance(h, DBLogHandler) for h in picker_logger.handlers):
        picker_db_handler = DBLogHandler(app=flask_app)
        picker_db_handler.setLevel(logging.INFO)
        picker_logger.addHandler(picker_db_handler)
    
    # ルートロガーには重要なエラーのみ
    root_logger = logging.getLogger()
    if not any(isinstance(h, DBLogHandler) for h in root_logger.handlers):
        root_db_handler = DBLogHandler(app=flask_app)
        root_db_handler.setLevel(logging.ERROR)  # Only capture errors in root logger
        root_logger.addHandler(root_db_handler)

# Setup logging when app is created
with flask_app.app_context():
    setup_celery_logging()

class ContextTask(celery.Task):
    """Make celery tasks work with Flask app context."""
    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            return self.run(*args, **kwargs)
    
    def log_error(self, message, event="celery_task", exc_info=None):
        """Log error to database with proper context."""
        import logging
        logger = logging.getLogger('celery.task')
        
        # Create LogRecord with additional attributes
        extra = {
            'event': event,
            'path': f"{self.name}",
            'request_id': getattr(self, 'request', {}).get('id', None)
        }
        
        if exc_info:
            logger.error(message, exc_info=exc_info, extra=extra)
        else:
            logger.error(message, extra=extra)

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
