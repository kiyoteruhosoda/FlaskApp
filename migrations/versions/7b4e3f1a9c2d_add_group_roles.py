"""add group_roles table (T8: グループとロールの紐づけ)

グループにロールを付与し、所属ユーザーへ権限を波及させる仕組みを追加する。
``group_roles`` 中間テーブルで ``user_group`` と ``role`` を多対多で結ぶ。

Revision ID: 7b4e3f1a9c2d
Revises: 6a3f7d2e1b4c
Create Date: 2026-07-08

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "7b4e3f1a9c2d"
down_revision = "6a3f7d2e1b4c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_roles",
        sa.Column(
            "group_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["group_id"], ["user_group.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"]),
        sa.PrimaryKeyConstraint("group_id", "role_id"),
        sa.UniqueConstraint("group_id", "role_id", name="uq_group_roles"),
    )


def downgrade() -> None:
    op.drop_table("group_roles")
