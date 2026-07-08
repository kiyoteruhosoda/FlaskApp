"""add impersonation_audit_log table and admin:impersonate permission

運用管理者による成り代わり（Impersonation）機能のための:
- ``impersonation_audit_log`` テーブル追加
- ``admin:impersonate`` 権限コード追加 + admin ロールへの付与

Revision ID: 9d6e4a2b0f5c
Revises: 8c5d2f3e1a4b
Create Date: 2026-07-08

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9d6e4a2b0f5c"
down_revision = "8c5d2f3e1a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- impersonation_audit_log テーブル作成 ---
    op.create_table(
        "impersonation_audit_log",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "impersonator_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "impersonated_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event", sa.String(16), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_impersonation_audit_log_impersonator_id",
        "impersonation_audit_log",
        ["impersonator_id"],
    )
    op.create_index(
        "ix_impersonation_audit_log_impersonated_id",
        "impersonation_audit_log",
        ["impersonated_id"],
    )
    op.create_index(
        "ix_impersonation_audit_log_created_at",
        "impersonation_audit_log",
        ["created_at"],
    )

    # --- admin:impersonate 権限コード追加 ---
    bind = op.get_bind()

    # 権限コードを追加（既存の場合はスキップ）
    existing = bind.execute(
        sa.text("SELECT code FROM permissions WHERE code = 'admin:impersonate'")
    ).fetchone()
    if not existing:
        bind.execute(
            sa.text("INSERT INTO permissions (code) VALUES ('admin:impersonate')")
        )

    # admin ロールに付与
    permission_row = bind.execute(
        sa.text("SELECT id FROM permissions WHERE code = 'admin:impersonate'")
    ).fetchone()
    admin_role_row = bind.execute(
        sa.text("SELECT id FROM roles WHERE name = 'admin'")
    ).fetchone()

    if permission_row and admin_role_row:
        already_granted = bind.execute(
            sa.text(
                "SELECT 1 FROM role_permissions "
                "WHERE role_id = :rid AND permission_id = :pid"
            ),
            {"rid": admin_role_row[0], "pid": permission_row[0]},
        ).fetchone()
        if not already_granted:
            bind.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "VALUES (:rid, :pid)"
                ),
                {"rid": admin_role_row[0], "pid": permission_row[0]},
            )


def downgrade() -> None:
    # --- admin:impersonate 権限削除 ---
    bind = op.get_bind()

    permission_row = bind.execute(
        sa.text("SELECT id FROM permissions WHERE code = 'admin:impersonate'")
    ).fetchone()
    if permission_row:
        bind.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id = :pid"),
            {"pid": permission_row[0]},
        )
        bind.execute(
            sa.text("DELETE FROM permissions WHERE code = 'admin:impersonate'")
        )

    # --- impersonation_audit_log テーブル削除 ---
    op.drop_index("ix_impersonation_audit_log_created_at", "impersonation_audit_log")
    op.drop_index("ix_impersonation_audit_log_impersonated_id", "impersonation_audit_log")
    op.drop_index("ix_impersonation_audit_log_impersonator_id", "impersonation_audit_log")
    op.drop_table("impersonation_audit_log")
