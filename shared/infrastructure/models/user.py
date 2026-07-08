from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional, TYPE_CHECKING

from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.kernel.database.db import db
from shared.infrastructure.models.group import group_user_membership
from werkzeug.security import generate_password_hash, check_password_hash


if TYPE_CHECKING:  # pragma: no cover
    from shared.infrastructure.models.google_account import GoogleAccount
    from bounded_contexts.totp.infrastructure.totp_models import TOTPCredential
    from shared.infrastructure.models.passkey import PasskeyCredential
    from shared.infrastructure.models.group import Group


# Define BIGINT type compatible with SQLite auto increment
BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")

# --- 中間テーブル ---
user_roles = db.Table(
    "user_roles",
    db.Column("user_id", BigInt, db.ForeignKey("user.id"), primary_key=True),
    db.Column("role_id", BigInt, db.ForeignKey("role.id"), primary_key=True),
)

role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", BigInt, db.ForeignKey("role.id"), primary_key=True),
    db.Column("perm_id", BigInt, db.ForeignKey("permission.id"), primary_key=True),
)


class Role(db.Model):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(db.String(80), unique=True, nullable=False)  # 'admin' 等
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
    )
    users: Mapped[list["User"]] = relationship(
        "User",
        secondary=user_roles,
        back_populates="roles",
    )


class Permission(db.Model):
    __tablename__ = "permission"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(db.String(120), unique=True, nullable=False)  # 'reservation:create' 等
    detail: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    roles: Mapped[list[Role]] = relationship(
        "Role",
        secondary=role_permissions,
        back_populates="permissions",
    )


class User(db.Model):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(db.String(255), unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(db.String(80), nullable=True)  # ユーザー名フィールドを追加
    password_hash: Mapped[str] = mapped_column(db.String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    totp_secret: Mapped[str | None] = mapped_column(db.String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(db.Boolean, default=True, nullable=False)
    # API リフレッシュトークンを検証するためのハッシュ
    refresh_token_hash: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    # 初回ログイン時パスワード強制変更フラグ
    must_change_password: Mapped[bool] = mapped_column(db.Boolean, default=False, nullable=False, server_default="0")

    # 追加：ロール関連
    roles: Mapped[list[Role]] = relationship(
        "Role",
        secondary=user_roles,
        back_populates="users",
    )
    groups: Mapped[list["Group"]] = relationship(
        "Group",
        secondary=group_user_membership,
        back_populates="users",
    )
    google_accounts: Mapped[list["GoogleAccount"]] = relationship(
        "GoogleAccount",
        back_populates="user",
    )
    totp_credentials: Mapped[list["TOTPCredential"]] = relationship(
        "TOTPCredential",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    passkey_credentials: Mapped[list["PasskeyCredential"]] = relationship(
        "PasskeyCredential",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="PasskeyCredential.created_at",
    )

    # ヘルパ
    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    # リフレッシュトークンの管理ヘルパ
    def set_refresh_token(self, token: Optional[str]) -> None:
        if not token:
            self.refresh_token_hash = None
            return

        self.refresh_token_hash = generate_password_hash(token)

    def check_refresh_token(self, token: str) -> bool:
        if not self.refresh_token_hash:
            return False
        return check_password_hash(self.refresh_token_hash, token)

    # 認可ヘルパ
    def _iter_effective_roles(self) -> Iterable["Role"]:
        roles: list[Role] = list(self.roles or [])
        if not roles:
            return []
        return roles

    def _iter_group_roles(self) -> Iterable["Role"]:
        """所属グループに付与されたロールを返す（重複除去済み）."""
        seen_ids: set[int] = set()
        for group in (self.groups or []):
            for role in (group.roles or []):
                if role.id not in seen_ids:
                    seen_ids.add(role.id)
                    yield role

    @property
    def active_role(self) -> Optional["Role"]:
        return None

    @property
    def permissions(self) -> set[str]:
        codes = set()
        for r in self._iter_effective_roles():
            for p in r.permissions:
                codes.add(p.code)
        for r in self._iter_group_roles():
            for p in r.permissions:
                codes.add(p.code)
        return codes

    @property
    def all_permissions(self) -> set[str]:
        codes = set()
        for role in self.roles or []:
            for permission in role.permissions:
                codes.add(permission.code)
        for role in self._iter_group_roles():
            for permission in role.permissions:
                codes.add(permission.code)
        return codes

    def can(self, *codes: str) -> bool:
        have = self.permissions
        return any(c in have for c in codes)

    @property
    def display_name(self) -> str:
        """表示用の名前を取得（username > emailのローカル部分の順）"""
        if self.username:
            return self.username
        if self.email:
            return self.email.split('@')[0]
        return 'Unknown User'

