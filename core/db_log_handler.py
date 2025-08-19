import logging
from sqlalchemy import insert

from .db import db
from .models.log import Log


class DBLogHandler(logging.Handler):
    """Logging handler that persists logs to the database."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            trace = None
            if record.exc_info:
                formatter = logging.Formatter()
                trace = formatter.formatException(record.exc_info)
            with db.engine.begin() as conn:
                stmt = insert(Log).values(
                    level=record.levelname,
                    message=record.getMessage(),
                    trace=trace,
                    path=getattr(record, "path", None),
                    request_id=getattr(record, "request_id", None),
                )
                conn.execute(stmt)
        except Exception:
            pass
