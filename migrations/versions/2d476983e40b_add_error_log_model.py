"""add error log model

Revision ID: 2d476983e40b
Revises: 25126feee70c
Create Date: 2025-08-18 06:50:29.761068

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2d476983e40b'
down_revision = '25126feee70c'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'error_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('level', sa.String(length=50), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('trace', sa.Text(), nullable=True),
        sa.Column('path', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table('error_log')
