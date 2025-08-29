from datetime import datetime, timezone
import hashlib

from core.db import db

BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class RefreshToken(db.Model):
    """JWTリフレッシュトークン"""
    __tablename__ = "refresh_token"

    id = db.Column(BigInt, primary_key=True, autoincrement=True)
    user_id = db.Column(BigInt, db.ForeignKey("user.id"), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    user = db.relationship("User", backref="refresh_tokens")

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
