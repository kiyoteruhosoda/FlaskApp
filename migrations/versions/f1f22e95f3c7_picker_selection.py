from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f1f22e95f3c7'
down_revision = '02a871f6064b'
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table('picked_media_item', 'picker_selection')
    with op.batch_alter_table('picker_selection') as batch:
        batch.drop_constraint('uq_picked_media_item_session_media', type_='unique')
        batch.alter_column('picker_session_id', new_column_name='session_id')
        batch.alter_column('media_item_id', new_column_name='google_media_id')
        batch.add_column(sa.Column('error_msg', sa.Text(), nullable=True))
        batch.add_column(sa.Column('base_url', sa.Text(), nullable=True))
        batch.add_column(sa.Column('locked_by', sa.String(length=255), nullable=True))
        batch.add_column(sa.Column('lock_heartbeat_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('last_transition_at', sa.DateTime(), nullable=True))
        batch.create_unique_constraint('uq_picker_selection_session_media', ['session_id', 'google_media_id'])
    op.create_index('idx_picker_selection_session_status', 'picker_selection', ['session_id', 'status'])
    op.create_index('idx_picker_selection_status_lock', 'picker_selection', ['status', 'lock_heartbeat_at'])


def downgrade():
    op.drop_index('idx_picker_selection_status_lock', table_name='picker_selection')
    op.drop_index('idx_picker_selection_session_status', table_name='picker_selection')
    with op.batch_alter_table('picker_selection') as batch:
        batch.drop_constraint('uq_picker_selection_session_media', type_='unique')
        batch.drop_column('last_transition_at')
        batch.drop_column('lock_heartbeat_at')
        batch.drop_column('locked_by')
        batch.drop_column('base_url')
        batch.drop_column('error_msg')
        batch.alter_column('google_media_id', new_column_name='media_item_id')
        batch.alter_column('session_id', new_column_name='picker_session_id')
        batch.create_unique_constraint('uq_picked_media_item_session_media', ['picker_session_id', 'media_item_id'])
    op.rename_table('picker_selection', 'picked_media_item')
