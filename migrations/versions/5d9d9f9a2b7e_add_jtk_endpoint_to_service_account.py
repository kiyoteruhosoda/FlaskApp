"""add jtk endpoint to service account"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5d9d9f9a2b7e'
down_revision = 'd1f6a0f9035e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'service_account',
        sa.Column('jtk_endpoint', sa.String(length=500), nullable=True),
    )
    op.alter_column(
        'service_account',
        'public_key',
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'service_account',
        'public_key',
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_column('service_account', 'jtk_endpoint')
