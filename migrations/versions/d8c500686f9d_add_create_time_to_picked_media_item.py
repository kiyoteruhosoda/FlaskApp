"""add create_time to picked_media_item

Revision ID: d8c500686f9d
Revises: 02a871f6064b
Create Date: 2025-08-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd8c500686f9d'
down_revision = '02a871f6064b'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('picked_media_item', sa.Column('create_time', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('picked_media_item', 'create_time')
