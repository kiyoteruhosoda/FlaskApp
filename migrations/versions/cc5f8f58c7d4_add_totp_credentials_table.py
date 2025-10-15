"""Add TOTP credential storage"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cc5f8f58c7d4'
down_revision = 'b8c4a5d5630a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'totp_credential',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
        sa.Column('account', sa.String(length=255), nullable=False),
        sa.Column('issuer', sa.String(length=255), nullable=False),
        sa.Column('secret', sa.String(length=160), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('algorithm', sa.String(length=16), nullable=False, server_default='SHA1'),
        sa.Column('digits', sa.SmallInteger(), nullable=False, server_default='6'),
        sa.Column('period', sa.SmallInteger(), nullable=False, server_default='30'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account', 'issuer', name='uq_totp_account_issuer'),
    )


def downgrade():
    op.drop_table('totp_credential')
