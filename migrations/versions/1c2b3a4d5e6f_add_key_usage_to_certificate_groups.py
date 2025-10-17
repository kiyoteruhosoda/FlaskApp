from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "1c2b3a4d5e6f"
down_revision = "2f6e4c3b1a2d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind else ""

    json_type = sa.JSON().with_variant(
        postgresql.JSONB(astext_type=sa.Text()), "postgresql"
    )

    op.add_column(
        "certificate_groups",
        sa.Column("key_usage", json_type, nullable=True),
    )

    if dialect in {"mysql", "mariadb"}:
        op.create_check_constraint(
            "ck_certificate_groups_key_usage_json",
            "certificate_groups",
            "json_valid(key_usage)",
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind else ""

    if dialect in {"mysql", "mariadb"}:
        op.drop_constraint(
            "ck_certificate_groups_key_usage_json",
            "certificate_groups",
            type_="check",
        )

    op.drop_column("certificate_groups", "key_usage")
