"""add totp secret to user

Revision ID: 6d1ad4f0b9a0
Revises: d54264ebcb65
Create Date: 2025-08-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6d1ad4f0b9a0'
down_revision = 'd54264ebcb65'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user', sa.Column('totp_secret', sa.String(length=32), nullable=True))


def downgrade():
    op.drop_column('user', 'totp_secret')

