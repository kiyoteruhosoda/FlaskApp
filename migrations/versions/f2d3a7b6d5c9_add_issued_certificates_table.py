"""add issued certificates table"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f2d3a7b6d5c9"
down_revision = "e1f1aa7a3c5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "issued_certificates",
        sa.Column("kid", sa.String(length=64), primary_key=True),
        sa.Column("usage_type", sa.String(length=32), nullable=False),
        sa.Column("certificate_pem", sa.Text(), nullable=False),
        sa.Column(
            "jwk",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_issued_certificates_usage_type",
        "issued_certificates",
        ["usage_type"],
    )
    op.create_index(
        "ix_issued_certificates_issued_at",
        "issued_certificates",
        ["issued_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_issued_certificates_issued_at", table_name="issued_certificates")
    op.drop_index("ix_issued_certificates_usage_type", table_name="issued_certificates")
    op.drop_table("issued_certificates")
