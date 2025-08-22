"""Add picker_selection tracking fields

Revision ID: f6b6320b86d4
Revises: 02a871f6064b
Create Date: 2025-08-20 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f6b6320b86d4'
down_revision = '02a871f6064b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('picked_media_item', schema=None) as batch_op:
        batch_op.add_column(sa.Column('enqueued_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('started_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('finished_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('base_url_fetched_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('base_url_valid_until', sa.DateTime(), nullable=True))

        old_status = sa.Enum(
            'pending', 'imported', 'dup', 'failed', 'expired', 'skipped',
            name='picked_media_item_status'
        )
        new_status = sa.Enum(
            'pending', 'enqueued', 'running', 'imported', 'dup', 'failed', 'expired', 'skipped',
            name='picked_media_item_status'
        )
        batch_op.alter_column(
            'status',
            existing_type=old_status,
            type_=new_status,
            existing_nullable=False,
            existing_server_default='pending'
        )

        batch_op.drop_constraint('uq_picked_media_item_session_media', type_='unique')
        batch_op.create_unique_constraint('uq_picked_media_item_session_media', ['picker_session_id', 'media_item_id'])

    op.execute("UPDATE picked_media_item SET status='pending'")


def downgrade():
    op.execute("UPDATE picked_media_item SET status='pending' WHERE status IN ('enqueued', 'running')")
    with op.batch_alter_table('picked_media_item', schema=None) as batch_op:
        batch_op.drop_constraint('uq_picked_media_item_session_media', type_='unique')

        new_status = sa.Enum(
            'pending', 'enqueued', 'running', 'imported', 'dup', 'failed', 'expired', 'skipped',
            name='picked_media_item_status'
        )
        old_status = sa.Enum(
            'pending', 'imported', 'dup', 'failed', 'expired', 'skipped',
            name='picked_media_item_status'
        )
        batch_op.alter_column(
            'status',
            existing_type=new_status,
            type_=old_status,
            existing_nullable=False,
            existing_server_default='pending'
        )

        batch_op.drop_column('base_url_valid_until')
        batch_op.drop_column('base_url_fetched_at')
        batch_op.drop_column('attempts')
        batch_op.drop_column('finished_at')
        batch_op.drop_column('started_at')
        batch_op.drop_column('enqueued_at')

        batch_op.create_unique_constraint('uq_picked_media_item_session_media', ['picker_session_id', 'media_item_id'])
