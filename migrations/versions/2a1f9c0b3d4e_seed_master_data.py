"""seed master data (roles / permissions / admin)

init_master（スキーマ）の直後に、認可マスタデータを冪等に投入する
データマイグレーション。値は ``shared.domain.auth.master_data`` を唯一の
出所として参照し、投入スクリプトとの二重管理を避ける。

管理者の初期パスワードは環境変数 ``ADMIN_INITIAL_PASSWORD``（平文）で
上書きできる。未指定時はカタログのフォールバックハッシュ（平文 "admin"）を
使用するため、本番では初回ログイン後に必ず変更すること。

Revision ID: 2a1f9c0b3d4e
Revises: init_master
Create Date: 2026-06-28

"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

from shared.domain.auth.master_data import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_ID,
    DEFAULT_ADMIN_PASSWORD_HASH,
    DEFAULT_ADMIN_ROLE,
    DEFAULT_ADMIN_USERNAME,
    PERMISSION_CODES,
    ROLE_PERMISSIONS,
    ROLES,
)

# revision identifiers, used by Alembic.
revision = "2a1f9c0b3d4e"
down_revision = "init_master"
branch_labels = None
depends_on = None


def _resolve_admin_password_hash() -> str:
    """環境変数があれば平文をハッシュ化し、無ければフォールバックを返す。"""

    raw = os.environ.get("ADMIN_INITIAL_PASSWORD")
    if raw:
        from werkzeug.security import generate_password_hash

        return generate_password_hash(raw)
    return DEFAULT_ADMIN_PASSWORD_HASH


def upgrade() -> None:
    conn = op.get_bind()

    # --- ロール（id 固定）---------------------------------------------------
    for role_id, name in ROLES:
        exists = conn.execute(
            sa.text("SELECT 1 FROM role WHERE id = :id"), {"id": role_id}
        ).first()
        if not exists:
            conn.execute(
                sa.text("INSERT INTO role (id, name) VALUES (:id, :name)"),
                {"id": role_id, "name": name},
            )

    # --- 権限コード（id は DB 採番、code を安定キーに）-----------------------
    for code in PERMISSION_CODES:
        exists = conn.execute(
            sa.text("SELECT 1 FROM permission WHERE code = :code"), {"code": code}
        ).first()
        if not exists:
            conn.execute(
                sa.text("INSERT INTO permission (code) VALUES (:code)"),
                {"code": code},
            )

    # --- ロールへの権限付与 -------------------------------------------------
    for role_name, codes in ROLE_PERMISSIONS.items():
        role_row = conn.execute(
            sa.text("SELECT id FROM role WHERE name = :name"), {"name": role_name}
        ).first()
        if not role_row:
            continue
        role_id = role_row[0]
        for code in codes:
            perm_row = conn.execute(
                sa.text("SELECT id FROM permission WHERE code = :code"), {"code": code}
            ).first()
            if not perm_row:
                continue
            perm_id = perm_row[0]
            linked = conn.execute(
                sa.text(
                    "SELECT 1 FROM role_permissions "
                    "WHERE role_id = :role_id AND perm_id = :perm_id"
                ),
                {"role_id": role_id, "perm_id": perm_id},
            ).first()
            if not linked:
                conn.execute(
                    sa.text(
                        "INSERT INTO role_permissions (role_id, perm_id) "
                        "VALUES (:role_id, :perm_id)"
                    ),
                    {"role_id": role_id, "perm_id": perm_id},
                )

    # --- 初期管理者 --------------------------------------------------------
    admin_row = conn.execute(
        sa.text("SELECT id FROM user WHERE email = :email"),
        {"email": DEFAULT_ADMIN_EMAIL},
    ).first()
    if not admin_row:
        conn.execute(
            sa.text(
                "INSERT INTO user (id, email, password_hash, username, created_at, is_active) "
                "VALUES (:id, :email, :pw, :username, :created_at, :is_active)"
            ),
            {
                "id": DEFAULT_ADMIN_ID,
                "email": DEFAULT_ADMIN_EMAIL,
                "pw": _resolve_admin_password_hash(),
                "username": DEFAULT_ADMIN_USERNAME,
                "created_at": datetime.now(timezone.utc),
                "is_active": True,
            },
        )
        admin_id = DEFAULT_ADMIN_ID
    else:
        admin_id = admin_row[0]

    admin_role_row = conn.execute(
        sa.text("SELECT id FROM role WHERE name = :name"), {"name": DEFAULT_ADMIN_ROLE}
    ).first()
    if admin_role_row:
        admin_role_id = admin_role_row[0]
        linked = conn.execute(
            sa.text(
                "SELECT 1 FROM user_roles WHERE user_id = :uid AND role_id = :rid"
            ),
            {"uid": admin_id, "rid": admin_role_id},
        ).first()
        if not linked:
            conn.execute(
                sa.text(
                    "INSERT INTO user_roles (user_id, role_id) VALUES (:uid, :rid)"
                ),
                {"uid": admin_id, "rid": admin_role_id},
            )


def downgrade() -> None:
    conn = op.get_bind()

    # 初期管理者とロール紐付け
    admin_row = conn.execute(
        sa.text("SELECT id FROM user WHERE email = :email"),
        {"email": DEFAULT_ADMIN_EMAIL},
    ).first()
    if admin_row:
        admin_id = admin_row[0]
        conn.execute(
            sa.text("DELETE FROM user_roles WHERE user_id = :uid"), {"uid": admin_id}
        )
        conn.execute(sa.text("DELETE FROM user WHERE id = :uid"), {"uid": admin_id})

    # ロール権限付与
    for role_name, codes in ROLE_PERMISSIONS.items():
        role_row = conn.execute(
            sa.text("SELECT id FROM role WHERE name = :name"), {"name": role_name}
        ).first()
        if not role_row:
            continue
        role_id = role_row[0]
        for code in codes:
            perm_row = conn.execute(
                sa.text("SELECT id FROM permission WHERE code = :code"), {"code": code}
            ).first()
            if not perm_row:
                continue
            conn.execute(
                sa.text(
                    "DELETE FROM role_permissions "
                    "WHERE role_id = :role_id AND perm_id = :perm_id"
                ),
                {"role_id": role_id, "perm_id": perm_row[0]},
            )

    # 権限コード
    for code in PERMISSION_CODES:
        conn.execute(
            sa.text("DELETE FROM permission WHERE code = :code"), {"code": code}
        )

    # ロール
    for role_id, _name in ROLES:
        conn.execute(sa.text("DELETE FROM role WHERE id = :id"), {"id": role_id})
