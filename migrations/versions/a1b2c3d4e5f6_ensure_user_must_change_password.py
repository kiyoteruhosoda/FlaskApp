"""ensure user.must_change_password exists (reconciliation)

``6a3f7d2e1b4c`` で ``user.must_change_password`` を追加したが、既に
``alembic_version`` がその先のリビジョンまで進んでいた環境では当該
マイグレーションが再実行されず、カラムが物理的に欠落したまま
``alembic upgrade head`` が no-op になる不整合が発生していた
（ログイン時に ``Unknown column 'user.must_change_password'`` で失敗）。

このマイグレーションはヘッドの後ろに置き、カラムが存在しない場合のみ
追加する冪等な補正を行う。既に存在する環境（新規構築を含む）では
何もしないため、スキーマの乖離は生じない。

Revision ID: a1b2c3d4e5f6
Revises: 9d6e4a2b0f5c
Create Date: 2026-07-10

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "9d6e4a2b0f5c"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    if _has_column("user", "must_change_password"):
        return
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
    # 補正専用マイグレーションのため、down では何もしない
    # （カラム自体の管理は 6a3f7d2e1b4c が担う）。
    pass
