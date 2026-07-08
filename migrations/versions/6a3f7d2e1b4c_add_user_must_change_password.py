"""add must_change_password to user

初回ログイン時のパスワード強制変更フロー（REQUIRE_PASSWORD_CHANGE_ON_FIRST_LOGIN 設定）
に対応するため、``user`` テーブルに以下を追加する。

- ``must_change_password``: ログイン後にパスワード変更を要求するフラグ
  （既存ユーザーは False で埋める）。

Revision ID: 6a3f7d2e1b4c
Revises: 5f2b8d4c7e10
Create Date: 2026-07-08

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "6a3f7d2e1b4c"
down_revision = "5f2b8d4c7e10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("must_change_password")
