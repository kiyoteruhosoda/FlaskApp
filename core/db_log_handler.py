import json
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Optional, Set

from flask import current_app, has_app_context
from sqlalchemy import insert, create_engine
from sqlalchemy.engine import Engine

from .db import db

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
            uri = os.environ.get("DATABASE_URI") or "sqlite:///application_logs.db"
            self._fallback_engine = create_engine(uri, future=True)
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
        log_model = _get_log_model()
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

        try:
            log_model = _get_log_model()
            with engine.begin() as conn:
                stmt = insert(log_model).values(
                    level=record.levelname,
                    message=message_json,
                    trace=trace,
                    path=path_value,
                    request_id=request_id,
                    event=event,
                )
                conn.execute(stmt)
        except Exception as exc:  # pragma: no cover - escalate for visibility
            raise RuntimeError("Failed to persist log record to database") from exc
def _get_log_model():
    from .models.log import Log  # Local import to avoid circular dependencies

    return Log

