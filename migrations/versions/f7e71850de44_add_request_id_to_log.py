"""add request_id to log

Revision ID: f7e71850de44
Revises: f2b317d264e2
Create Date: 2025-08-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7e71850de44'
down_revision = 'f2b317d264e2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('log', sa.Column('request_id', sa.String(length=36), nullable=True))


def downgrade():
    op.drop_column('log', 'request_id')

