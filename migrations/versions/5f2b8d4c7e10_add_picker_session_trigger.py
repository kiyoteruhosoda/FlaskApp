"""record what triggered a picker session

「作業が何のきっかけで始まったか（誰の操作か／自動か）」をセッション自体に
記録できるよう、``picker_session`` に以下を追加する。

- ``trigger``: セッション作成のきっかけ（"user"=人の操作 / "worker"=自動処理）。
  既存行はきっかけ不明のため "unknown" で埋める。語彙は ``job_sync.trigger`` に合わせる。
- ``triggered_by_user_id``: trigger が "user" のときに操作したユーザー（``user.id``）。
  自動起動時は NULL。

Revision ID: 5f2b8d4c7e10
Revises: 4c8d1e2f5a09
Create Date: 2026-07-05

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "5f2b8d4c7e10"
down_revision = "4c8d1e2f5a09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("picker_session", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "trigger",
                sa.String(length=32),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.add_column(
            sa.Column(
                "triggered_by_user_id",
                sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_picker_session_triggered_by_user_id_user",
            "user",
            ["triggered_by_user_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("picker_session", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_picker_session_triggered_by_user_id_user", type_="foreignkey"
        )
        batch_op.drop_column("triggered_by_user_id")
        batch_op.drop_column("trigger")
