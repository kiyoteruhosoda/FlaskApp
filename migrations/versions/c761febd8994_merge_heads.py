"""merge_heads

Revision ID: c761febd8994
Revises: 0f1a2b3c4d5e, 1a2b3c4d5e78, 8c1f2e3d4b5a, 9b1e5f7c8d6e, a4e3d9f2c5ab, c7d8e9f0a1b2, f0e1d2c3b4a5
Create Date: 2025-11-05 00:15:11.899740

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c761febd8994'
down_revision = ('0f1a2b3c4d5e', '1a2b3c4d5e78', '8c1f2e3d4b5a', '9b1e5f7c8d6e', 'a4e3d9f2c5ab', 'c7d8e9f0a1b2', 'f0e1d2c3b4a5')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
