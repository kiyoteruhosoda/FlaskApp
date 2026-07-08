"""add user_preference table

ユーザーごとの設定（例: スライドショー表示間隔）を保持する
``user_preference`` テーブルを追加する。

Revision ID: 8c5d2f3e1a4b
Revises: 7b4e3f1a9c2d
Create Date: 2026-07-08

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "8c5d2f3e1a4b"
down_revision = "7b4e3f1a9c2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preference",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_user_preference_user_key"),
    )
    op.create_index(
        op.f("ix_user_preference_user_id"), "user_preference", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_user_preference_user_id"), table_name="user_preference")
    op.drop_table("user_preference")
