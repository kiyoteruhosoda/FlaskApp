"""create google_account table

Revision ID: a1e8c8d084a9
Revises: 6d1ad4f0b9a0
Create Date: 2025-08-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1e8c8d084a9'
down_revision = '6d1ad4f0b9a0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'google_account',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('scopes', sa.Text(), nullable=False),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('oauth_token_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_google_account_email', 'google_account', ['email'], unique=True)


def downgrade():
    op.drop_index('ix_google_account_email', table_name='google_account')
    op.drop_table('google_account')
