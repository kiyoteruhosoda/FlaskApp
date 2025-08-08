from datetime import datetime
from flask_login import UserMixin
from ..extensions import db, login_manager
from werkzeug.security import generate_password_hash, check_password_hash


# --- 中間テーブル ---
user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("role.id"), primary_key=True),
)

role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.Integer, db.ForeignKey("role.id"), primary_key=True),
    db.Column("perm_id", db.Integer, db.ForeignKey("permission.id"), primary_key=True),
)

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)  # 'admin' 等
    permissions = db.relationship("Permission", secondary=role_permissions, backref="roles")

class Permission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(120), unique=True, nullable=False)  # 'reservation:create' 等



class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 追加：ロール関連
    roles = db.relationship("Role", secondary=user_roles, backref="users")

    # ヘルパ
    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    # 認可ヘルパ
    @property
    def permissions(self) -> set[str]:
        codes = set()
        for r in self.roles:
            for p in r.permissions:
                codes.add(p.code)
        return codes

    def has_role(self, *names: str) -> bool:
        have = {r.name for r in self.roles}
        return any(n in have for n in names)

    def can(self, *codes: str) -> bool:
        have = self.permissions
        return any(c in have for c in codes)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
