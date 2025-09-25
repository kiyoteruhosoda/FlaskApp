from datetime import datetime, timezone
import json

from core.db import db

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class PickerSession(db.Model):
    __tablename__ = "picker_session"

    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    account_id = db.Column(BigInt, db.ForeignKey("google_account.id"), nullable=True)  # ローカルインポート用にNULL許可
    session_id = db.Column(db.String(255), unique=True, nullable=True)
    picker_uri = db.Column(db.Text, nullable=True)
    expire_time = db.Column(db.DateTime, nullable=True)
    polling_config_json = db.Column(db.Text, nullable=True)
    picking_config_json = db.Column(db.Text, nullable=True)
    media_items_set = db.Column(db.Boolean, nullable=True)
    status = db.Column(
        db.Enum(
            "pending",
            "ready",
            "expanding",
            "processing",
            "enqueued",
            "importing",
            "imported",
            "canceled",
            "expired",
            "error",
            "failed",
            name="picker_session_status",
        ),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    selected_count = db.Column(db.Integer, nullable=True)
    stats_json = db.Column(db.Text, nullable=True)
    last_polled_at = db.Column(db.DateTime, nullable=True)
    last_progress_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=True
    )
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    account = db.relationship(
        "GoogleAccount",
        backref="picker_sessions",
        lazy="selectin",
    )

    def stats(self):
        try:
            return json.loads(self.stats_json) if self.stats_json else {}
        except Exception:
            return {}

    def set_stats(self, data):
        self.stats_json = json.dumps(data)
