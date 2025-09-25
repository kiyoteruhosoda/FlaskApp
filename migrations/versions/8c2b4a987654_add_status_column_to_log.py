"""Add status column to log table

Revision ID: 8c2b4a987654
Revises: 31b1901dba43
Create Date: 2024-05-09 00:00:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8c2b4a987654'
down_revision = '31b1901dba43'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('log', sa.Column('status', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('log', 'status')
