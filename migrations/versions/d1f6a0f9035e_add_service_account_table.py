"""Add service_account table for machine authenticated access."""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1f6a0f9035e'
down_revision = 'cc5f8f58c7d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    timestamp = sa.DateTime().with_variant(sa.DateTime(fsp=6), 'mysql')
    op.create_table(
        'service_account',
        sa.Column(
            'service_account_id',
            sa.BigInteger().with_variant(sa.Integer(), 'sqlite'),
            nullable=False,
            autoincrement=True,
        ),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('public_key', sa.Text(), nullable=False),
        sa.Column('scope_names', sa.String(length=1000), nullable=False, server_default=''),
        sa.Column('active_flg', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            'reg_dttm',
            timestamp,
            nullable=False,
            server_default=sa.text('UTC_TIMESTAMP(6)'),
        ),
        sa.Column(
            'mod_dttm',
            timestamp,
            nullable=False,
            server_default=sa.text('UTC_TIMESTAMP(6)'),
            mysql_on_update=sa.text('UTC_TIMESTAMP(6)'),
        ),
        sa.PrimaryKeyConstraint('service_account_id'),
        sa.UniqueConstraint('name'),
    )


def downgrade() -> None:
    op.drop_table('service_account')
