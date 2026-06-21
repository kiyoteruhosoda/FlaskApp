from __future__ import annotations

"""add progress_step column to worker_log

Revision ID: f7b8c9d0e1f2
Revises: d3f8a1c2b5e6
Create Date: 2024-07-12 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f7b8c9d0e1f2"
down_revision = "d3f8a1c2b5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "worker_log",
        sa.Column("progress_step", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_worker_log_file_task_id_progress_step",
        "worker_log",
        ["file_task_id", "progress_step"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_worker_log_file_task_id_progress_step",
        table_name="worker_log",
    )
    op.drop_column("worker_log", "progress_step")
