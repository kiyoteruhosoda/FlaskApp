from __future__ import annotations

"""add permission detail column

Revision ID: f0e1d2c3b4a5
Revises: a8b5c1d2e3f4
Create Date: 2024-05-20 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f0e1d2c3b4a5"
down_revision = "a8b5c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("permission", sa.Column("detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("permission", "detail")
