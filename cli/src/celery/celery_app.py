import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from celery import Celery, signals
from celery.exceptions import Retry as CeleryRetry
from dotenv import load_dotenv
from flask import Flask

from shared.kernel.celery_settings import CelerySettings
from shared.kernel.database.db import db
from shared.infrastructure.models.celery_task import CeleryTaskRecord, CeleryTaskStatus
from shared.infrastructure.models.job_sync import JobSync
from shared.kernel.logging.logging_config import log_task_info
from presentation.web import _apply_persisted_settings
from presentation.web.bootstrap.config import BaseApplicationSettings

# shared.infrastructure.models.__init__ は shared モデル（User・GoogleAccount 等）を
# import する。これらは bounded_context のモデルを文字列 relationship で参照しているため、
# SQLAlchemy マッパー構成前に全依存モデルを登録する必要がある。
# 具体的な cross-context 参照:
#   User.totp_credentials       → TOTPCredential (totp context)
#   GoogleAccount.picker_sessions → PickerSession (picker_import context)
#   GoogleAccount.media_items    → Media (photonest context)
import bounded_contexts.totp.infrastructure.totp_models as _totp_models  # noqa: F401
import bounded_contexts.picker_import.infrastructure.picker_session as _picker_session_mod  # noqa: F401
import bounded_contexts.photonest.infrastructure.photo_models as _photo_models  # noqa: F401

# .envファイルを読み込み
load_dotenv()

# Flask app factory
def create_app():
    """Create and configure Flask app for Celery."""
    app = Flask(__name__)
    app.config.from_object(BaseApplicationSettings)

    # Initialize database
    db.init_app(app)

    # Initialize other extensions
    from presentation.web.bootstrap.extensions import migrate, login_manager, babel
    migrate.init_app(app, db)
    login_manager.init_app(app)
    babel.init_app(app)

    # Load persisted configuration so Celery shares runtime settings with the web app
    with app.app_context():
        _apply_persisted_settings(app)

    return app

# Create Flask app context for Celery tasks
flask_app = create_app()

with flask_app.app_context():
    celery_runtime_settings = CelerySettings.from_application_settings()

# Create Celery instance
celery = Celery(
    'cli.src.celery.celery_app',
    broker=celery_runtime_settings.broker_url,
    backend=celery_runtime_settings.result_backend,
)

# Configure Celery
celery.conf.update(celery_runtime_settings.as_mapping())

def setup_celery_logging():
    """Setup logging for Celery workers to use worker_log and console output."""
    from shared.kernel.logging.db_log_handler import DBLogHandler, WorkerDBLogHandler
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


def _ensure_worker_logging() -> None:
    """Attach logging handlers within an application context."""

    with flask_app.app_context():
        setup_celery_logging()


@signals.worker_process_init.connect
def _dispose_db_engine_after_fork(**_: Any) -> None:
    """Discard inherited DB connections in each forked prefork worker.

    ``flask_app = create_app()`` above runs at module import time, i.e. in the
    Celery master process, and ``_apply_persisted_settings()`` already opens a
    real DB connection through ``db.engine`` during that call. Celery's
    default ``--pool=prefork`` then forks worker child processes from that
    master, so every child inherits the *same* open connection/socket in the
    pool. If two processes (parent/sibling children) later use that inherited
    connection concurrently, the MySQL protocol stream gets corrupted between
    them, which surfaces as bizarre, hard-to-reproduce SQLAlchemy-internal
    errors (e.g. ``NotImplementedError`` deep in ORM row processing) on the
    first query a forked child runs. Disposing the engine right after fork
    forces each child to open its own fresh connections instead of reusing
    the parent's.
    """

    with flask_app.app_context():
        db.engine.dispose()


@signals.worker_process_init.connect
def _configure_worker_process_logging(**_: Any) -> None:
    """Ensure each Celery worker process attaches the DB log handler."""

    _ensure_worker_logging()


@signals.beat_init.connect
def _configure_beat_logging(**_: Any) -> None:
    """Ensure Celery beat also sends logs to the database."""

    _ensure_worker_logging()


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


def _safe_dump_json(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except TypeError:
        return json.dumps(str(data), ensure_ascii=False)


def _extract_queue_name(request: Any) -> Optional[str]:
    delivery = getattr(request, "delivery_info", None) or {}
    candidate = (
        delivery.get("routing_key")
        or delivery.get("queue")
        or delivery.get("exchange")
    )
    if isinstance(candidate, dict):
        candidate = candidate.get("name") or candidate.get("routing_key")
    if isinstance(candidate, str):
        candidate = candidate.strip() or None
    return candidate


def _detect_trigger_source(request: Any) -> str:
    headers = getattr(request, "headers", None) or {}
    if isinstance(headers, dict) and headers.get("periodic_task_name"):
        return "beat"
    return "worker"


def _serialize_call_signature(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> str:
    payload = {
        "args": list(args),
        "kwargs": kwargs,
    }
    return _safe_dump_json(payload)


def _ensure_job_sync_record(
    *,
    record: CeleryTaskRecord,
    task_name: str,
    started_at: datetime,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    request: Any,
) -> Tuple[Optional[JobSync], bool]:
    """Ensure there is a JobSync row for the running Celery task."""

    existing_job = record.job_syncs[-1] if record.job_syncs else None
    queue_name = _extract_queue_name(request)
    trigger = _detect_trigger_source(request)
    args_payload = _serialize_call_signature(args, kwargs)
    truncated_target = (task_name or "celery_task")[:50]

    created = False
    if existing_job is None:
        job = JobSync(
            target=truncated_target,
            task_name=task_name,
            queue_name=queue_name,
            trigger=trigger,
            celery_task=record,
            started_at=started_at,
            status="running",
            args_json=args_payload,
        )
        created = True
        db.session.add(job)
    else:
        job = existing_job
        if not job.task_name:
            job.task_name = task_name
        if queue_name and not job.queue_name:
            job.queue_name = queue_name
        if not job.trigger:
            job.trigger = trigger
        if job.started_at is None:
            job.started_at = started_at
        if job.status in {"queued", "running"}:
            job.status = "running"
        if not job.args_json or job.args_json == "{}":
            job.args_json = args_payload
        if not job.target:
            job.target = truncated_target

    return job, created


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


def _is_noop_cleanup_result(result: Any) -> bool:
    return isinstance(result, dict) and result.get("updated_count") == 0


def _is_noop_watchdog_result(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    return sum(v for v in result.values() if isinstance(v, int)) == 0


# 定期実行される housekeeping タスクのうち、実際に何も処理しなかった (no-op) 場合は
# 同期ジョブ履歴 (JobSync) / タスク記録 (CeleryTaskRecord) を残さないようにするための
# 判定関数レジストリ。high-frequency な監視タスクほど no-op が大半を占め、履歴が
# 本当に必要なエントリを埋もれさせてしまうため。
_NOOP_RESULT_PREDICATES: Dict[str, Any] = {
    "session_recovery.cleanup_stale_sessions": _is_noop_cleanup_result,
    "picker_import.watchdog": _is_noop_watchdog_result,
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
            record: Optional[CeleryTaskRecord] = None
            job: Optional[JobSync] = None
            job_created = False
            started_at = datetime.now(timezone.utc)
            lifecycle_logger = logging.getLogger("celery.task.lifecycle")
            request_obj = getattr(self, "request", None)

            try:
                object_identity = _resolve_task_object(self.name, args, kwargs)
                celery_task_id = getattr(request_obj, "id", None)
                eta = _normalize_dt(getattr(request_obj, "eta", None))

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

                job, job_created = _ensure_job_sync_record(
                    record=record,
                    task_name=self.name,
                    started_at=started_at,
                    args=args,
                    kwargs=kwargs,
                    request=request_obj,
                )

                db.session.commit()

                log_task_info(
                    lifecycle_logger,
                    _safe_dump_json(
                        {
                            "message": "Celery task started",
                            "task": self.name,
                            "celeryTaskId": celery_task_id,
                            "jobId": getattr(job, "id", None),
                            "queue": getattr(job, "queue_name", None),
                            "trigger": getattr(job, "trigger", None),
                        }
                    ),
                    event="celery.task.started",
                    task_name=self.name,
                    task_uuid=celery_task_id,
                    job_id=getattr(job, "id", None),
                    queue=getattr(job, "queue_name", None),
                    trigger=getattr(job, "trigger", None),
                )
            except Exception:
                _safe_db_rollback()
                record = None
                job = None

            try:
                result = self.run(*args, **kwargs)
            except CeleryRetry as retry_exc:
                retry_eta = _normalize_dt(
                    getattr(retry_exc, "when", None) or getattr(retry_exc, "eta", None)
                )
                if record is not None:
                    try:
                        record.status = CeleryTaskStatus.SCHEDULED
                        record.finished_at = None
                        if retry_eta:
                            record.scheduled_for = retry_eta
                        record.error_message = None
                        record.update_payload({"retry": True})
                        db.session.commit()
                    except Exception:
                        _safe_db_rollback()
                if job is not None:
                    try:
                        job.status = "queued"
                        job.finished_at = None
                        if job_created:
                            job.stats_json = _safe_dump_json(
                                {
                                    "retry": True,
                                    "retry_at": retry_eta.isoformat() if retry_eta else None,
                                }
                            )
                        db.session.commit()
                    except Exception:
                        _safe_db_rollback()
                    log_task_info(
                        lifecycle_logger,
                        _safe_dump_json(
                            {
                                "message": "Celery task retry scheduled",
                                "task": self.name,
                                "jobId": getattr(job, "id", None),
                                "retryEta": retry_eta.isoformat() if retry_eta else None,
                            }
                        ),
                        event="celery.task.retry",
                        task_name=self.name,
                        job_id=getattr(job, "id", None),
                        retry_eta=retry_eta.isoformat() if retry_eta else None,
                    )
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
                if job is not None and job.status in {"queued", "running"}:
                    try:
                        job.status = "failed"
                        job.finished_at = datetime.now(timezone.utc)
                        if job_created:
                            job.stats_json = _safe_dump_json({"error": str(exc)})
                        db.session.commit()
                    except Exception:
                        _safe_db_rollback()
                    log_task_info(
                        lifecycle_logger,
                        _safe_dump_json(
                            {
                                "message": "Celery task failed",
                                "task": self.name,
                                "jobId": getattr(job, "id", None),
                                "error": str(exc),
                            }
                        ),
                        event="celery.task.failed",
                        task_name=self.name,
                        job_id=getattr(job, "id", None),
                        error=str(exc),
                    )
                raise
            else:
                noop_predicate = _NOOP_RESULT_PREDICATES.get(self.name)
                is_noop_run = (
                    job_created
                    and noop_predicate is not None
                    and noop_predicate(result)
                )

                if is_noop_run:
                    # 何も処理しなかった定期実行はジョブ履歴・タスク記録を残さない。
                    try:
                        if job is not None:
                            db.session.delete(job)
                        if record is not None:
                            db.session.delete(record)
                        db.session.commit()
                    except Exception:
                        _safe_db_rollback()
                    return result

                if record is not None:
                    try:
                        record.status = CeleryTaskStatus.SUCCESS
                        record.finished_at = datetime.now(timezone.utc)
                        payload = result if isinstance(result, dict) else {"value": result}
                        record.set_result(payload)
                        db.session.commit()
                    except Exception:
                        _safe_db_rollback()
                if job is not None and job.status in {"queued", "running"}:
                    try:
                        job.status = "success"
                        job.finished_at = datetime.now(timezone.utc)
                        if job_created:
                            job.stats_json = _safe_dump_json(result)
                        db.session.commit()
                    except Exception:
                        _safe_db_rollback()
                    log_task_info(
                        lifecycle_logger,
                        _safe_dump_json(
                            {
                                "message": "Celery task finished",
                                "task": self.name,
                                "jobId": getattr(job, "id", None),
                            }
                        ),
                        event="celery.task.succeeded",
                        task_name=self.name,
                        job_id=getattr(job, "id", None),
                    )
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
    "logs-cleanup": {
        "task": "logs.cleanup",
        "schedule": timedelta(days=1),  # 毎日実行
        "kwargs": {"retention_days": 365},  # 1年以上前のログを削除
    },
    "certificates-auto-rotation": {
        "task": "certificates.auto_rotate",
        "schedule": timedelta(hours=1),
    },
}
