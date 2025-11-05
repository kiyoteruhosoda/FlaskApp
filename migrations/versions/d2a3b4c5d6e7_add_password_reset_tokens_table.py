"""add_password_reset_tokens_table

Revision ID: d2a3b4c5d6e7
Revises: c761febd8994
Create Date: 2025-11-05 00:16:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2a3b4c5d6e7'
down_revision = 'c761febd8994'
branch_labels = None
depends_on = None


def upgrade():
    # Create password_reset_token table
    op.create_table(
        'password_reset_token',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), primary_key=True, autoincrement=True),
        sa.Column('email', sa.String(255), nullable=False, index=True),
        sa.Column('token_hash', sa.String(255), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )


def downgrade():
    op.drop_table('password_reset_token')
