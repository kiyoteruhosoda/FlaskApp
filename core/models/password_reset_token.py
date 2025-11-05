"""Password reset token model."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Mapped, mapped_column
from werkzeug.security import generate_password_hash, check_password_hash

from core.db import db


# Define BIGINT type compatible with SQLite auto increment
BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


class PasswordResetToken(db.Model):
    """パスワードリセットトークンを管理するモデル。
    
    セキュリティ要件:
    - トークンはハッシュ化して保存
    - 有効期限は30分
    - 一度使用したら再利用不可
    """
    __tablename__ = "password_reset_token"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(db.String(255), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(db.String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(db.DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime, 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    def set_token(self, raw_token: str) -> None:
        """トークンをハッシュ化して保存する。"""
        self.token_hash = generate_password_hash(raw_token)

    def check_token(self, raw_token: str) -> bool:
        """トークンを検証する。"""
        return check_password_hash(self.token_hash, raw_token)

    def is_valid(self) -> bool:
        """トークンが有効かどうかをチェックする。"""
        now = datetime.now(timezone.utc)
        return not self.used and self.expires_at > now

    @classmethod
    def create_token(
        cls, 
        email: str, 
        raw_token: str,
        validity_minutes: int = 30
    ) -> "PasswordResetToken":
        """新しいパスワードリセットトークンを作成する。
        
        Args:
            email: ユーザーのメールアドレス
            raw_token: 平文のトークン（ハッシュ化される）
            validity_minutes: トークンの有効期限（分）
            
        Returns:
            作成されたPasswordResetTokenインスタンス
        """
        token = cls(
            email=email,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=validity_minutes)
        )
        token.set_token(raw_token)
        return token

    def mark_as_used(self) -> None:
        """トークンを使用済みとしてマークする。"""
        self.used = True
