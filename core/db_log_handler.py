import json
import logging
import sys
import traceback
from typing import TYPE_CHECKING, Any, Dict, Optional, Set

from flask import current_app, has_app_context
from sqlalchemy import insert, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DataError, OperationalError

from .db import db
from .settings import settings

if TYPE_CHECKING:  # pragma: no cover
    from flask import Flask


_RESERVED_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "stacklevel",
}


def _extract_extras(record: logging.LogRecord) -> Dict[str, Any]:
    """Return custom attributes attached to *record* for persistence."""

    extras: Dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in _RESERVED_ATTRS or key in {"event", "path", "request_id"}:
            continue
        if key.startswith("_"):
            continue
        extras[key] = value
    return extras


class DBLogHandler(logging.Handler):
    """Logging handler that persists logs to the database."""

    def __init__(self, app: Optional["Flask"] = None, *, engine: Optional[Engine] = None) -> None:
        super().__init__()
        self._app = app
        self._engine: Optional[Engine] = engine
        self._fallback_engine: Optional[Engine] = None
        self._ensured_engines: Set[int] = set()

    def bind_to_app(self, app: "Flask") -> None:
        """Rebind this handler to *app* and reset cached engines."""

        self._app = app
        self._engine = None
        self._fallback_engine = None
        self._ensured_engines.clear()

    def _resolve_engine(self) -> Engine:
        if self._engine is not None:
            return self._engine

        app = None
        if has_app_context():
            app = current_app._get_current_object()
        elif self._app is not None:
            app = self._app

        if app is not None:
            try:
                if has_app_context():
                    engine = db.engine
                else:
                    with app.app_context():
                        engine = db.engine
            except Exception as exc:  # pragma: no cover - unexpected misconfiguration
                raise RuntimeError("Failed to acquire database engine from Flask app") from exc
            engine = self._maybe_use_fallback(engine)
            self._engine = engine
            return engine

        try:
            engine_attr = getattr(db, "engine")
        except RuntimeError:
            engine_attr = None
        except AttributeError:
            engine_attr = None
        if engine_attr is not None:
            engine_attr = self._maybe_use_fallback(engine_attr)
            self._engine = engine_attr
            return engine_attr

        engine = self._get_fallback_engine()
        self._engine = engine
        return engine

    def _get_fallback_engine(self) -> Engine:
        if self._fallback_engine is None:
            self._fallback_engine = create_engine(settings.logs_database_uri, future=True)
        return self._fallback_engine

    def _maybe_use_fallback(self, engine: Engine) -> Engine:
        if isinstance(engine, Engine):
            try:
                database = engine.url.database
            except Exception:  # pragma: no cover - unexpected URL structure
                database = None
            if database in (None, "", ":memory:"):
                return self._get_fallback_engine()
        return engine

    def _ensure_table(self, engine: Engine) -> None:
        marker = id(engine)
        if marker in self._ensured_engines:
            return
        if not isinstance(engine, Engine):  # pragma: no cover - supports mocks in tests
            return
        log_model = self._get_log_model()
        log_model.__table__.create(bind=engine, checkfirst=True)
        self._ensured_engines.add(marker)

    def emit(self, record: logging.LogRecord) -> None:
        trace = None
        if record.exc_info:
            formatter = logging.Formatter()
            trace = formatter.formatException(record.exc_info)

        raw_message = record.getMessage()
        try:
            payload = json.loads(raw_message)
        except Exception:
            payload = {"message": raw_message}

        status_value = getattr(record, "status", None)
        if status_value is not None:
            payload.setdefault("status", status_value)

        # Attach metadata for better traceability.
        payload.setdefault("_meta", {})
        payload["_meta"].update(
            {
                "logger": record.name,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "level": record.levelname,
            }
        )

        extras = _extract_extras(record)
        if extras:
            payload["_extra"] = extras

        event = getattr(record, "event", None)
        if not event:
            event = record.name or "general"
        event = str(event)[:50]

        path_value = getattr(record, "path", None)
        if not path_value:
            path_value = getattr(record, "pathname", None)
        if isinstance(path_value, str):
            path_value = path_value[:255]

        request_id = getattr(record, "request_id", None)
        if request_id is not None:
            request_id = str(request_id)[:36]

        message_json = json.dumps(payload, ensure_ascii=False, default=str)

        engine = self._resolve_engine()
        self._ensure_table(engine)

        log_model = self._get_log_model()
        stmt = insert(log_model).values(
            **self._build_insert_values(
                record=record,
                message_json=message_json,
                trace=trace,
                event=event,
                path_value=path_value,
                request_id=request_id,
                payload=payload,
                extras=extras,
            )
        )

        def _persist(engine_to_use: Engine) -> None:
            with engine_to_use.begin() as conn:
                conn.execute(stmt)

        try:
            _persist(engine)
            return
        except Exception as exc:  # pragma: no cover - escalate for visibility
            handled = isinstance(exc, (DataError, OperationalError))
            if handled:
                fallback_engine = self._get_fallback_engine()
                if fallback_engine is not engine:
                    try:
                        self._ensure_table(fallback_engine)
                        _persist(fallback_engine)
                        return
                    except Exception:
                        pass

                traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
                return

            raise RuntimeError("Failed to persist log record to database") from exc

    def _get_log_model(self):
        from .models.log import Log  # Local import to avoid circular dependencies

        return Log

    def _build_insert_values(
        self,
        *,
        record: logging.LogRecord,
        message_json: str,
        trace: Optional[str],
        event: str,
        path_value: Optional[str],
        request_id: Optional[str],
        payload: Dict[str, Any],
        extras: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "level": record.levelname,
            "message": message_json,
            "trace": trace,
            "path": path_value,
            "request_id": request_id,
            "event": event,
        }


class WorkerDBLogHandler(DBLogHandler):
    """Logging handler dedicated to persisting Celery worker logs."""

    def _get_log_model(self):
        from .models.worker_log import WorkerLog  # Local import to avoid circular dependencies

        return WorkerLog

    @staticmethod
    def _truncate(value: Optional[Any], max_length: int) -> Optional[str]:
        if value is None:
            return None
        value_str = str(value)
        if max_length and len(value_str) > max_length:
            return value_str[:max_length]
        return value_str

    @staticmethod
    def _coerce_jsonable(value: Optional[Any]) -> Optional[Any]:
        if value is None:
            return None
        try:
            json.dumps(value, ensure_ascii=False)
            return value
        except TypeError:
            return json.loads(json.dumps(value, ensure_ascii=False, default=str))

    def _build_insert_values(
        self,
        *,
        record: logging.LogRecord,
        message_json: str,
        trace: Optional[str],
        event: str,
        path_value: Optional[str],  # Unused but kept for signature compatibility
        request_id: Optional[str],  # Unused but kept for signature compatibility
        payload: Dict[str, Any],
        extras: Dict[str, Any],
    ) -> Dict[str, Any]:
        def _get_from_payload(*keys: str) -> Optional[Any]:
            for key in keys:
                if key in payload:
                    return payload[key]
            return None

        payload_task_name = _get_from_payload("task_name", "task")
        payload_task_uuid = _get_from_payload("task_uuid", "task_id", "uuid", "id")
        payload_worker_hostname = _get_from_payload("worker_hostname", "hostname")
        payload_queue_name = _get_from_payload("queue_name", "queue")

        task_name = (
            getattr(record, "task_name", None)
            or extras.get("task_name")
            or payload_task_name
        )
        task_uuid = (
            getattr(record, "task_id", None)
            or getattr(record, "task_uuid", None)
            or extras.get("task_id")
            or extras.get("task_uuid")
            or payload_task_uuid
        )
        worker_hostname = (
            getattr(record, "hostname", None)
            or extras.get("hostname")
            or payload_worker_hostname
        )
        queue_name = (
            getattr(record, "queue", None)
            or getattr(record, "queue_name", None)
            or extras.get("queue")
            or extras.get("queue_name")
            or payload_queue_name
        )
        if isinstance(queue_name, dict):
            queue_name = queue_name.get("name") or queue_name.get("routing_key")

        status = payload.get("status")

        meta_json = self._coerce_jsonable(payload.get("_meta"))
        extra_json = self._coerce_jsonable(payload.get("_extra"))

        return {
            "level": self._truncate(record.levelname, 20),
            "event": event,
            "logger_name": self._truncate(record.name, 120),
            "task_name": self._truncate(task_name, 255),
            "task_uuid": self._truncate(task_uuid, 36),
            "worker_hostname": self._truncate(worker_hostname, 255),
            "queue_name": self._truncate(queue_name, 120),
            "status": self._truncate(status, 40),
            "message": message_json,
            "trace": trace,
            "meta_json": meta_json,
            "extra_json": extra_json,
        }

