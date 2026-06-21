"""Add perceptual hash support for media duplicates."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c7d8e9f0a1b2"
down_revision = "a7d9c3e2b1f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media", sa.Column("phash", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_media_phash_dimensions",
        "media",
        ["phash", "shot_at", "width", "height", "duration_ms", "is_video"],
    )


def downgrade() -> None:
    op.drop_index("ix_media_phash_dimensions", table_name="media")
    op.drop_column("media", "phash")
