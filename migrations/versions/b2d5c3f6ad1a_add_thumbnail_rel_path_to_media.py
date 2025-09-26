"""Add thumbnail_rel_path column to media table."""

from alembic import op
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = "b2d5c3f6ad1a"
down_revision = "a8b078766f1e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media",
        sa.Column("thumbnail_rel_path", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("media", "thumbnail_rel_path")
