from datetime import datetime, timezone

from ..db import db


BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class WorkerLog(db.Model):
    __tablename__ = "worker_log"

    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    level = db.Column(db.String(20), nullable=False)
    event = db.Column(db.String(50), nullable=False)
    logger_name = db.Column(db.String(120))
    task_name = db.Column(db.String(255))
    task_uuid = db.Column(db.String(36))
    worker_hostname = db.Column(db.String(255))
    queue_name = db.Column(db.String(120))
    status = db.Column(db.String(40))
    message = db.Column(db.Text, nullable=False)
    trace = db.Column(db.Text)
    meta_json = db.Column(db.JSON)
    extra_json = db.Column(db.JSON)


__all__ = ["WorkerLog"]
