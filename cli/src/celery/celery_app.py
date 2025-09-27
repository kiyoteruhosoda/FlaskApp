import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from celery import Celery
from celery.exceptions import Retry as CeleryRetry
from dotenv import load_dotenv
from flask import Flask

from core.db import db
from core.models.celery_task import CeleryTaskRecord, CeleryTaskStatus
from webapp.config import Config

# .envファイルを読み込み
load_dotenv()

# Flask app factory
def create_app():
    """Create and configure Flask app for Celery."""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Initialize database
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
    """Setup logging for Celery workers to use worker_log and console output."""
    from core.db_log_handler import DBLogHandler, WorkerDBLogHandler
    import sys

    # ログフォーマッター
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    def _remove_legacy_db_handlers(logger: logging.Logger) -> None:
        for handler in list(logger.handlers):
            if isinstance(handler, DBLogHandler) and not isinstance(handler, WorkerDBLogHandler):
                logger.removeHandler(handler)
                try:
                    handler.close()
                except Exception:
                    pass

    def _ensure_worker_db_handler(logger: logging.Logger, level: int = logging.INFO) -> None:
        for handler in logger.handlers:
            if isinstance(handler, WorkerDBLogHandler):
                handler.setLevel(level)
                break
        else:
            worker_handler = WorkerDBLogHandler(app=flask_app)
            worker_handler.setLevel(level)
            logger.addHandler(worker_handler)

    # Get Celery logger
    celery_logger = logging.getLogger('celery')
    celery_logger.setLevel(logging.INFO)

    # コンソール（Docker）ログハンドラー
    if not any(isinstance(h, logging.StreamHandler) for h in celery_logger.handlers):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        celery_logger.addHandler(console_handler)

    _remove_legacy_db_handlers(celery_logger)
    _ensure_worker_db_handler(celery_logger, logging.INFO)

    # タスク用のロガー設定
    task_logger = logging.getLogger('celery.task')
    task_logger.setLevel(logging.INFO)

    # タスクロガーにもコンソールハンドラーを追加
    if not any(isinstance(h, logging.StreamHandler) for h in task_logger.handlers):
        task_console_handler = logging.StreamHandler(sys.stdout)
        task_console_handler.setLevel(logging.INFO)
        task_console_handler.setFormatter(formatter)
        task_logger.addHandler(task_console_handler)

    _remove_legacy_db_handlers(task_logger)
    _ensure_worker_db_handler(task_logger, logging.INFO)

    # picker_import 専用ロガーの設定
    picker_logger = logging.getLogger('picker_import')
    picker_logger.setLevel(logging.INFO)

    # picker専用ロガーにもハンドラーを追加
    if not any(isinstance(h, logging.StreamHandler) for h in picker_logger.handlers):
        picker_console_handler = logging.StreamHandler(sys.stdout)
        picker_console_handler.setLevel(logging.INFO)
        picker_console_handler.setFormatter(formatter)
        picker_logger.addHandler(picker_console_handler)

    _remove_legacy_db_handlers(picker_logger)
    _ensure_worker_db_handler(picker_logger, logging.INFO)

    # ルートロガーには重要なエラーのみ
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.ERROR)
    _remove_legacy_db_handlers(root_logger)
    _ensure_worker_db_handler(root_logger, logging.ERROR)

# Setup logging when app is created
with flask_app.app_context():
    setup_celery_logging()


def _to_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        return str(value)
    except Exception:
        return None


def _normalize_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return None


def _resolve_thumbnail_identity(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    media_id = kwargs.get("media_id")
    if media_id is None and args:
        media_id = args[0]
    return "media", _to_str(media_id)


def _resolve_local_import_identity(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    session_id = kwargs.get("session_id")
    if session_id is None and args:
        session_id = args[0]
    return "local_import_session", _to_str(session_id)


def _resolve_picker_item_identity(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    selection_id = kwargs.get("selection_id")
    if selection_id is None and args:
        selection_id = args[0]
    return "picker_selection", _to_str(selection_id)


_TASK_IDENTITY_RESOLVERS: Dict[str, Any] = {
    "thumbs.generate": _resolve_thumbnail_identity,
    "local_import.run": _resolve_local_import_identity,
    "picker_import.item": _resolve_picker_item_identity,
    "thumbnail_retry.process_due": lambda *_: ("system", "thumbnail-retry-monitor"),
}


def _resolve_task_object(name: str, args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    resolver = _TASK_IDENTITY_RESOLVERS.get(name)
    if resolver is None:
        return (None, None)
    try:
        identity = resolver(args, kwargs)
    except Exception:
        return (None, None)
    if not isinstance(identity, tuple) or len(identity) != 2:
        return (None, None)
    return identity


def _safe_db_rollback() -> None:
    try:
        db.session.rollback()
    except Exception:
        pass

class ContextTask(celery.Task):
    """Make celery tasks work with Flask app context."""
    def __call__(self, *args, **kwargs):
        with flask_app.app_context():
            record = None
            started_at = datetime.now(timezone.utc)
            try:
                object_identity = _resolve_task_object(self.name, args, kwargs)
                celery_task_id = getattr(getattr(self, "request", None), "id", None)
                eta = _normalize_dt(getattr(getattr(self, "request", None), "eta", None))

                record = CeleryTaskRecord.get_or_create(
                    task_name=self.name,
                    celery_task_id=celery_task_id,
                    object_identity=object_identity,
                )
                if eta:
                    record.scheduled_for = eta
                record.status = CeleryTaskStatus.RUNNING
                record.started_at = started_at
                record.update_payload({
                    "args": list(args),
                    "kwargs": kwargs,
                })
                db.session.commit()
            except Exception:
                _safe_db_rollback()
                record = None

            try:
                result = self.run(*args, **kwargs)
            except CeleryRetry as retry_exc:
                if record is not None:
                    try:
                        record.status = CeleryTaskStatus.SCHEDULED
                        record.finished_at = None
                        retry_eta = _normalize_dt(getattr(retry_exc, "when", None) or getattr(retry_exc, "eta", None))
                        if retry_eta:
                            record.scheduled_for = retry_eta
                        record.error_message = None
                        record.update_payload({"retry": True})
                        db.session.commit()
                    except Exception:
                        _safe_db_rollback()
                raise
            except Exception as exc:
                if record is not None:
                    try:
                        record.status = CeleryTaskStatus.FAILED
                        record.finished_at = datetime.now(timezone.utc)
                        record.error_message = str(exc)
                        db.session.commit()
                    except Exception:
                        _safe_db_rollback()
                raise
            else:
                if record is not None:
                    try:
                        record.status = CeleryTaskStatus.SUCCESS
                        record.finished_at = datetime.now(timezone.utc)
                        payload = result if isinstance(result, dict) else {"value": result}
                        record.set_result(payload)
                        db.session.commit()
                    except Exception:
                        _safe_db_rollback()
                return result
    
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
    "thumbnail-retry-monitor": {
        "task": "thumbnail_retry.process_due",
        "schedule": timedelta(minutes=1),
    },
    "backup-cleanup": {
        "task": "backup_cleanup.cleanup",
        "schedule": timedelta(days=1),  # 毎日実行
        "kwargs": {"retention_days": 30},  # 30日より古いファイルを削除
    },
}
