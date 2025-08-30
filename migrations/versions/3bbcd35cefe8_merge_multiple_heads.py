"""Merge multiple heads

Revision ID: 3bbcd35cefe8
Revises: 4344a1c01532, c097ec524158
Create Date: 2025-08-30 10:03:01.146031

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3bbcd35cefe8'
down_revision = ('4344a1c01532', 'c097ec524158')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
