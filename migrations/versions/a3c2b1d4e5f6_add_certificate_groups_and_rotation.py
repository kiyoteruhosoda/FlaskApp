"""add certificate groups and rotation columns"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "a3c2b1d4e5f6"
down_revision = "f2d3a7b6d5c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind else ""

    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

    op.create_table(
        "certificate_groups",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("group_code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("auto_rotate", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rotation_threshold_days", sa.Integer(), nullable=False),
        sa.Column("key_type", sa.String(length=16), nullable=False),
        sa.Column("key_curve", sa.String(length=32), nullable=True),
        sa.Column("key_size", sa.Integer(), nullable=True),
        sa.Column("subject", json_type, nullable=False),
        sa.Column("usage_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("group_code", name="uq_certificate_groups_group_code"),
    )
    op.create_index(
        "ix_certificate_groups_usage_type",
        "certificate_groups",
        ["usage_type"],
    )
    if dialect in {"mysql", "mariadb"}:
        op.create_check_constraint(
            "ck_certificate_groups_subject_json",
            "certificate_groups",
            "json_valid(subject)",
        )

    op.add_column("issued_certificates", sa.Column("group_id", sa.BigInteger(), nullable=True))
    op.add_column("issued_certificates", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.add_column(
        "issued_certificates",
        sa.Column("auto_rotated_from_kid", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_issued_certificates_expires_at",
        "issued_certificates",
        ["expires_at"],
    )
    op.create_foreign_key(
        "fk_issued_certificates_group_id_certificate_groups",
        "issued_certificates",
        "certificate_groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind else ""

    op.drop_constraint(
        "fk_issued_certificates_group_id_certificate_groups",
        "issued_certificates",
        type_="foreignkey",
    )
    op.drop_index("ix_issued_certificates_expires_at", table_name="issued_certificates")
    op.drop_column("issued_certificates", "auto_rotated_from_kid")
    op.drop_column("issued_certificates", "expires_at")
    op.drop_column("issued_certificates", "group_id")

    if dialect in {"mysql", "mariadb"}:
        op.drop_constraint(
            "ck_certificate_groups_subject_json",
            "certificate_groups",
            type_="check",
        )
    op.drop_index("ix_certificate_groups_usage_type", table_name="certificate_groups")
    op.drop_table("certificate_groups")
