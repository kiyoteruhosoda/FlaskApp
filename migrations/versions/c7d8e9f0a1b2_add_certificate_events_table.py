"""add certificate events table"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c7d8e9f0a1b2"
down_revision = "a3c2b1d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind else ""

    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    op.create_table(
        "certificate_events",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_kid", sa.String(length=64), nullable=True),
        sa.Column("target_group_code", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("details", json_type, nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_certificate_events_target_kid",
        "certificate_events",
        ["target_kid"],
    )
    op.create_index(
        "ix_certificate_events_target_group_code",
        "certificate_events",
        ["target_group_code"],
    )
    op.create_index(
        "ix_certificate_events_occurred_at",
        "certificate_events",
        ["occurred_at"],
    )

    if dialect in {"mysql", "mariadb"}:
        op.create_check_constraint(
            "ck_certificate_events_details_json",
            "certificate_events",
            "json_valid(details)",
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind else ""

    if dialect in {"mysql", "mariadb"}:
        op.drop_constraint(
            "ck_certificate_events_details_json",
            "certificate_events",
            type_="check",
        )

    op.drop_index("ix_certificate_events_occurred_at", table_name="certificate_events")
    op.drop_index("ix_certificate_events_target_group_code", table_name="certificate_events")
    op.drop_index("ix_certificate_events_target_kid", table_name="certificate_events")
    op.drop_table("certificate_events")
