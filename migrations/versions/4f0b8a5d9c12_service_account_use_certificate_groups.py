"""Link service accounts to certificate groups."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4f0b8a5d9c12"
down_revision = "b8c4a5d5630a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("service_account", schema=None) as batch_op:
        batch_op.drop_column("jwt_endpoint")
        batch_op.add_column(
            sa.Column("certificate_group_code", sa.String(length=64), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_service_account_certificate_group",
            "certificate_groups",
            ["certificate_group_code"],
            ["group_code"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("service_account", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_service_account_certificate_group", type_="foreignkey"
        )
        batch_op.drop_column("certificate_group_code")
        batch_op.add_column(sa.Column("jwt_endpoint", sa.String(length=500), nullable=True))
