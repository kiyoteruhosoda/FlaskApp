"""Remove status column from log table

Revision ID: 9f2c3d1a6b7e
Revises: 8c2b4a987654
Create Date: 2024-05-10 00:00:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f2c3d1a6b7e'
down_revision = '8c2b4a987654'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('log', schema=None) as batch_op:
        batch_op.drop_column('status')


def downgrade():
    with op.batch_alter_table('log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(length=50), nullable=True))
