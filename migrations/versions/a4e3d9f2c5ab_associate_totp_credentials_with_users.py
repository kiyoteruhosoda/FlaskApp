"""Associate TOTP credentials with user accounts"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a4e3d9f2c5ab"
down_revision = "cc5f8f58c7d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("totp_credential", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.BigInteger(), nullable=True))
        batch_op.drop_constraint("uq_totp_account_issuer", type_="unique")
        batch_op.create_unique_constraint(
            "uq_totp_user_account_issuer", ["user_id", "account", "issuer"]
        )

    op.create_index("ix_totp_credential_user_id", "totp_credential", ["user_id"])
    op.create_foreign_key(
        "fk_totp_credential_user_id_user",
        "totp_credential",
        "user",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    conn = op.get_bind()
    totp_table = sa.table(
        "totp_credential",
        sa.column("id", sa.BigInteger()),
        sa.column("account", sa.String()),
        sa.column("user_id", sa.BigInteger()),
    )
    user_table = sa.table(
        "user",
        sa.column("id", sa.BigInteger()),
        sa.column("email", sa.String()),
    )

    rows = conn.execute(sa.select(totp_table.c.id, totp_table.c.account)).all()
    if rows:
        user_rows = conn.execute(sa.select(user_table.c.id, user_table.c.email)).all()
        user_map = {email.lower(): user_id for user_id, email in user_rows if email}
        for totp_id, account in rows:
            if not account:
                continue
            owner = user_map.get(account.lower())
            if owner is not None:
                conn.execute(
                    totp_table.update()
                    .where(totp_table.c.id == totp_id)
                    .values(user_id=owner)
                )

        remaining = conn.execute(
            sa.select(totp_table.c.id).where(totp_table.c.user_id.is_(None))
        ).scalars()
        remaining_ids = list(remaining)
        if remaining_ids:
            fallback_user = conn.execute(
                sa.select(user_table.c.id).order_by(user_table.c.id.asc()).limit(1)
            ).scalar()
            if fallback_user is not None:
                conn.execute(
                    totp_table.update()
                    .where(totp_table.c.id.in_(remaining_ids))
                    .values(user_id=fallback_user)
                )
            else:
                conn.execute(
                    totp_table.delete().where(totp_table.c.id.in_(remaining_ids))
                )

    with op.batch_alter_table("totp_credential", schema=None) as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.BigInteger(), nullable=False)


def downgrade() -> None:
    op.drop_constraint("fk_totp_credential_user_id_user", "totp_credential", type_="foreignkey")
    op.drop_index("ix_totp_credential_user_id", table_name="totp_credential")
    with op.batch_alter_table("totp_credential", schema=None) as batch_op:
        batch_op.drop_constraint("uq_totp_user_account_issuer", type_="unique")
        batch_op.create_unique_constraint(
            "uq_totp_account_issuer", ["account", "issuer"]
        )
        batch_op.drop_column("user_id")
