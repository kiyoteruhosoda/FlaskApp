"""add passkey credentials table"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1a2b3c4d5e78'
down_revision = 'f3e2b1c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'passkey_credential',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('credential_id', sa.String(length=255), nullable=False),
        sa.Column('public_key', sa.Text(), nullable=False),
        sa.Column('sign_count', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('transports', sa.JSON(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('attestation_format', sa.String(length=64), nullable=True),
        sa.Column('aaguid', sa.String(length=64), nullable=True),
        sa.Column('backup_eligible', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('backup_state', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint('uq_passkey_credential_id', 'passkey_credential', ['credential_id'])
    op.create_index('ix_passkey_credential_user_id', 'passkey_credential', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_passkey_credential_user_id', table_name='passkey_credential')
    op.drop_constraint('uq_passkey_credential_id', 'passkey_credential', type_='unique')
    op.drop_table('passkey_credential')
