from datetime import datetime
from ..db import db


class Log(db.Model):
    __tablename__ = "log"

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    trace = db.Column(db.Text)
    path = db.Column(db.String(255))
    request_id = db.Column(db.String(36))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


__all__ = ["Log"]
