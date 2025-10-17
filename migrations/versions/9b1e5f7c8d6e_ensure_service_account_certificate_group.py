"""Ensure certificate group column exists for service accounts."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9b1e5f7c8d6e"
down_revision = "4f0b8a5d9c12"
branch_labels = None
depends_on = None


def _get_table_state(table_name: str) -> tuple[set[str], set[str]]:
    """Return column names and foreign key names for the given table."""
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys(table_name)}
    return columns, foreign_keys


def upgrade() -> None:
    columns, foreign_keys = _get_table_state("service_account")

    with op.batch_alter_table("service_account", schema=None) as batch_op:
        if "certificate_group_code" not in columns:
            batch_op.add_column(
                sa.Column("certificate_group_code", sa.String(length=64), nullable=True)
            )
        if "fk_service_account_certificate_group" not in foreign_keys:
            batch_op.create_foreign_key(
                "fk_service_account_certificate_group",
                "certificate_groups",
                ["certificate_group_code"],
                ["group_code"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    columns, foreign_keys = _get_table_state("service_account")

    with op.batch_alter_table("service_account", schema=None) as batch_op:
        if "fk_service_account_certificate_group" in foreign_keys:
            batch_op.drop_constraint(
                "fk_service_account_certificate_group", type_="foreignkey"
            )
        if "certificate_group_code" in columns:
            batch_op.drop_column("certificate_group_code")
