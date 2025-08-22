from datetime import datetime, timezone

from core.db import db

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")

class JobSync(db.Model):
    """Synchronization job record."""

    __tablename__ = "job_sync"

    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    target = db.Column(db.String(50), nullable=False)
    account_id = db.Column(BigInt, nullable=False)
    session_id = db.Column(BigInt, nullable=False)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="queued")
    stats_json = db.Column(db.Text, nullable=False, default="{}")


__all__ = ["JobSync"]

