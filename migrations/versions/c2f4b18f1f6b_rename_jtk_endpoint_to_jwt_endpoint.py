"""Rename service account endpoint column from jtk_endpoint to jwt_endpoint."""

from alembic import op


# revision identifiers, used by Alembic.
revision = "c2f4b18f1f6b"
down_revision = "a3c2b1d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("service_account") as batch_op:
        batch_op.alter_column("jtk_endpoint", new_column_name="jwt_endpoint")


def downgrade() -> None:
    with op.batch_alter_table("service_account") as batch_op:
        batch_op.alter_column("jwt_endpoint", new_column_name="jtk_endpoint")
