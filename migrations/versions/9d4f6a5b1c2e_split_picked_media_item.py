"""split picked media item

Revision ID: 9d4f6a5b1c2e
Revises: 446c8706cd16
Create Date: 2025-09-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9d4f6a5b1c2e'
down_revision = '446c8706cd16'
branch_labels = None
depends_on = None

BigInt = sa.BigInteger().with_variant(sa.Integer(), 'sqlite')

def upgrade():
    op.rename_table('picked_media_item', 'media_item')
    with op.batch_alter_table('media_item') as batch_op:
        batch_op.drop_column('base_url')
        batch_op.drop_column('status')
    op.create_table(
        'picked_media_item',
        sa.Column('id', BigInt, primary_key=True, autoincrement=True),
        sa.Column('picker_session_id', BigInt, sa.ForeignKey('picker_session.id'), nullable=False),
        sa.Column('media_item_id', sa.String(length=255), sa.ForeignKey('media_item.id'), nullable=False),
        sa.Column('base_url', sa.String(length=255)),
        sa.Column('status', sa.Enum('pending', 'imported', 'dup', 'failed', 'expired', 'skipped', name='picked_media_item_status'), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('picker_session_id', 'media_item_id', name='uniq_picker_session_media'),
    )
    with op.batch_alter_table('media_file_metadata') as batch_op:
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('picked_media_item_id')
        batch_op.add_column(sa.Column('media_item_id', sa.String(length=255), nullable=False))
        batch_op.create_foreign_key(None, 'media_item', ['media_item_id'], ['id'])
        batch_op.create_unique_constraint(None, ['media_item_id'])
    with op.batch_alter_table('picker_import_task') as batch_op:
        batch_op.drop_constraint('uk_task_session_item', type_='unique')
        batch_op.alter_column('picked_media_item_id', existing_type=sa.String(length=255), type_=BigInt, existing_nullable=False)
        batch_op.create_foreign_key(None, 'picked_media_item', ['picked_media_item_id'], ['id'])
        batch_op.create_unique_constraint('uk_task_session_item', ['picker_session_id', 'picked_media_item_id'])

def downgrade():
    with op.batch_alter_table('picker_import_task') as batch_op:
        batch_op.drop_constraint('uk_task_session_item', type_='unique')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.alter_column('picked_media_item_id', existing_type=BigInt, type_=sa.String(length=255), existing_nullable=False)
        batch_op.create_unique_constraint('uk_task_session_item', ['picker_session_id', 'picked_media_item_id'])
        batch_op.create_foreign_key(None, 'media_item', ['picked_media_item_id'], ['id'])
    with op.batch_alter_table('media_file_metadata') as batch_op:
        batch_op.drop_constraint(None, type_='unique')
        batch_op.drop_constraint(None, type_='foreignkey')
        batch_op.drop_column('media_item_id')
        batch_op.add_column(sa.Column('picked_media_item_id', sa.String(length=255), nullable=False))
        batch_op.create_foreign_key(None, 'media_item', ['picked_media_item_id'], ['id'])
    op.drop_table('picked_media_item')
    with op.batch_alter_table('media_item') as batch_op:
        batch_op.add_column(sa.Column('status', sa.Enum('pending', 'imported', 'dup', 'failed', 'expired', 'skipped', name='picked_media_item_status'), nullable=False, server_default='pending'))
        batch_op.add_column(sa.Column('base_url', sa.String(length=255)))
    op.rename_table('media_item', 'picked_media_item')
