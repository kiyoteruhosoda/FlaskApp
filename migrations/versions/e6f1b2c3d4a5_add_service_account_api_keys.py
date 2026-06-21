"""Add service account API key management tables"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e6f1b2c3d4a5"
down_revision = "c2f4b18f1f6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    timestamp = sa.DateTime(timezone=True).with_variant(
        sa.DateTime(timezone=True, fsp=6), "mysql"
    )
    bigint = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

    op.create_table(
        "service_account_api_key",
        sa.Column("api_key_id", bigint, autoincrement=True, nullable=False),
        sa.Column("service_account_id", bigint, nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("secret_hash", sa.String(length=255), nullable=False),
        sa.Column("scope_names", sa.String(length=2000), nullable=False),
        sa.Column("expires_at", timestamp, nullable=True),
        sa.Column("revoked_at", timestamp, nullable=True),
        sa.Column(
            "created_at",
            timestamp,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["service_account_id"],
            ["service_account.service_account_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("api_key_id"),
        sa.UniqueConstraint("public_id", name="uq_service_account_api_key_public_id"),
    )
    op.create_index(
        "ix_service_account_api_key_service_account_id",
        "service_account_api_key",
        ["service_account_id"],
    )

    op.create_table(
        "service_account_api_key_log",
        sa.Column("log_id", bigint, autoincrement=True, nullable=False),
        sa.Column("api_key_id", bigint, nullable=False),
        sa.Column(
            "accessed_at",
            timestamp,
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("endpoint", sa.String(length=255), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["api_key_id"],
            ["service_account_api_key.api_key_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("log_id"),
    )
    op.create_index(
        "ix_service_account_api_key_log_api_key_id",
        "service_account_api_key_log",
        ["api_key_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_service_account_api_key_log_api_key_id",
        table_name="service_account_api_key_log",
    )
    op.drop_table("service_account_api_key_log")
    op.drop_index(
        "ix_service_account_api_key_service_account_id",
        table_name="service_account_api_key",
    )
    op.drop_table("service_account_api_key")
