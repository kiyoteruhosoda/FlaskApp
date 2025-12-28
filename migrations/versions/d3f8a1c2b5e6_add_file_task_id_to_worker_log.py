from __future__ import annotations

"""add file_task_id column to worker_log

Revision ID: d3f8a1c2b5e6
Revises: d2a3b4c5d6e7
Create Date: 2024-05-14 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d3f8a1c2b5e6"
down_revision = "d2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "worker_log",
        sa.Column("file_task_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_worker_log_file_task_id",
        "worker_log",
        ["file_task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_worker_log_file_task_id", table_name="worker_log")
    op.drop_column("worker_log", "file_task_id")
