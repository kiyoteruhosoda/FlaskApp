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
            
            # eventがNoneの場合はデフォルト値を設定
            event = getattr(record, "event", None)
            if event is None:
                event = "general"
            
            with db.engine.begin() as conn:
                stmt = insert(Log).values(
                    level=record.levelname,
                    message=record.getMessage(),
                    trace=trace,
                    path=getattr(record, "path", None),
                    request_id=getattr(record, "request_id", None),
                    event=event, 
                )
                conn.execute(stmt)
        except Exception as e:
            print("DBLogHandler error:", e)
            pass
