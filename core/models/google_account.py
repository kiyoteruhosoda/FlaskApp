from datetime import datetime, timedelta, timezone
import json

from core.db import db
from core.crypto import decrypt

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")

class GoogleAccount(db.Model):
    __tablename__ = "google_account"
    __table_args__ = (
        db.UniqueConstraint('user_id', 'email', name='uq_user_google_email'),
    )

    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    user_id = db.Column(BigInt, db.ForeignKey("user.id"), nullable=True)
    email = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active")
    scopes = db.Column(db.Text, nullable=False)
    last_synced_at = db.Column(db.DateTime, nullable=True)
    oauth_token_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # リレーションシップ
    user = db.relationship("User", backref="google_accounts")

    def scopes_list(self):
        """Return scopes as list."""
        if not self.scopes:
            return []
        return [s.strip() for s in self.scopes.split(",") if s.strip()]

    def refresh_token_expires_at(self):
        """Return refresh token expiry timestamp in ISO format if available."""
        if not self.oauth_token_json:
            return None
        try:
            data = json.loads(decrypt(self.oauth_token_json))
        except Exception:
            return None

        expiry = data.get("refresh_token_expires_at") or data.get("refresh_token_expiry")
        if expiry:
            return expiry

        expires_in = data.get("refresh_token_expires_in")
        if expires_in:
            try:
                base = self.last_synced_at or datetime.now(timezone.utc)
                return (base + timedelta(seconds=int(expires_in))).isoformat()
            except Exception:
                return None
        return None
