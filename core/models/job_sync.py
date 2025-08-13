from datetime import datetime

from core.db import db


class JobSync(db.Model):
    """Synchronization job record."""

    __tablename__ = "job_sync"

    id = db.Column(db.Integer, primary_key=True)
    target = db.Column(db.String(50), nullable=False)
    account_id = db.Column(db.Integer, nullable=False)
    started_at = db.Column(db.DateTime, default=lambda: datetime.utcnow(), nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False)
    stats_json = db.Column(db.Text, nullable=False, default="{}")


__all__ = ["JobSync"]

