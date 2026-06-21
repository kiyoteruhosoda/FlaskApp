"""Add system settings table for persisted configuration."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "1f0a4c2b8d7e"
down_revision = ("4f0b8a5d9c12", "2f6e4c3b1a2d")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=120), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
