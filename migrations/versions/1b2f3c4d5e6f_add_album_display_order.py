"""Add display_order column to album"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1b2f3c4d5e6f'
down_revision = '0b8e6c31db7e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('album', sa.Column('display_order', sa.Integer(), nullable=True))
    op.execute('UPDATE album SET display_order = id')


def downgrade():
    op.drop_column('album', 'display_order')
