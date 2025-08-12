from datetime import datetime
from ..extensions import db


class GoogleAccount(db.Model):
    __tablename__ = "google_account"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")
    scopes = db.Column(db.Text, nullable=False)
    last_synced_at = db.Column(db.DateTime, nullable=True)
    oauth_token_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def scopes_list(self):
        """Return scopes as list."""
        if not self.scopes:
            return []
        return [s.strip() for s in self.scopes.split(",") if s.strip()]
