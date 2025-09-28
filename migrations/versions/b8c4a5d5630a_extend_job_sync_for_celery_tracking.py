"""Extend JobSync for Celery tracking"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8c4a5d5630a'
down_revision = '3d5e2c8f7a3b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'job_sync',
        sa.Column('task_name', sa.String(length=255), nullable=False, server_default=''),
    )
    op.add_column(
        'job_sync',
        sa.Column('queue_name', sa.String(length=120), nullable=True),
    )
    op.add_column(
        'job_sync',
        sa.Column('trigger', sa.String(length=32), nullable=False, server_default='worker'),
    )
    op.add_column(
        'job_sync',
        sa.Column('args_json', sa.Text(), nullable=False, server_default='{}'),
    )

    op.alter_column('job_sync', 'account_id', existing_type=sa.BigInteger(), nullable=True)
    op.alter_column('job_sync', 'session_id', existing_type=sa.BigInteger(), nullable=True)

    op.execute("UPDATE job_sync SET task_name = CASE WHEN task_name = '' OR task_name IS NULL THEN target ELSE task_name END")
    op.execute("UPDATE job_sync SET trigger = 'worker' WHERE trigger IS NULL OR trigger = ''")
    op.execute("UPDATE job_sync SET args_json = '{}' WHERE args_json IS NULL")


def downgrade() -> None:
    # Best effort downgrade: new rows without session/account associations are removed
    op.execute("DELETE FROM job_sync WHERE session_id IS NULL")
    op.execute("UPDATE job_sync SET account_id = 0 WHERE account_id IS NULL")

    op.alter_column('job_sync', 'session_id', existing_type=sa.BigInteger(), nullable=False)
    op.alter_column('job_sync', 'account_id', existing_type=sa.BigInteger(), nullable=False)

    op.drop_column('job_sync', 'args_json')
    op.drop_column('job_sync', 'trigger')
    op.drop_column('job_sync', 'queue_name')
    op.drop_column('job_sync', 'task_name')
