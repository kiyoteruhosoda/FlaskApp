"""Remove deprecated public_key column from service_account."""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0e7d64c89741'
down_revision = '5d9d9f9a2b7e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('service_account') as batch_op:
        batch_op.drop_column('public_key')


def downgrade() -> None:
    with op.batch_alter_table('service_account') as batch_op:
        batch_op.add_column(sa.Column('public_key', sa.Text(), nullable=True))
