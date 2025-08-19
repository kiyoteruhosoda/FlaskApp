"""add fields to picker_session

Revision ID: 8a3f8c12d5b1
Revises: cf11071ee19e
Create Date: 2025-03-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8a3f8c12d5b1'
down_revision = 'cf11071ee19e'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('picker_session', sa.Column('expire_time', sa.DateTime(), nullable=True))
    op.add_column('picker_session', sa.Column('polling_config_json', sa.Text(), nullable=True))
    op.add_column('picker_session', sa.Column('picking_config_json', sa.Text(), nullable=True))
    op.add_column('picker_session', sa.Column('media_items_set', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('picker_session', 'media_items_set')
    op.drop_column('picker_session', 'picking_config_json')
    op.drop_column('picker_session', 'polling_config_json')
    op.drop_column('picker_session', 'expire_time')
