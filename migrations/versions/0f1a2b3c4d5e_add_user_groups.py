from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0f1a2b3c4d5e"
down_revision = "f3e2b1c4d5e6"
branch_labels = None
depends_on = None


BIGINT = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
GROUP_MANAGE_CODE = "group:manage"
DEFAULT_GROUP_ROLES = ("admin",)


def upgrade() -> None:
    op.create_table(
        "user_group",
        sa.Column("id", BIGINT, primary_key=True, autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", BIGINT, nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["user_group.id"], name="fk_user_group_parent"),
        sa.UniqueConstraint("name", name="uq_user_group_name"),
    )

    op.create_table(
        "group_user_membership",
        sa.Column("group_id", BIGINT, nullable=False),
        sa.Column("user_id", BIGINT, nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["user_group.id"], name="fk_group_membership_group"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], name="fk_group_membership_user"),
        sa.PrimaryKeyConstraint("group_id", "user_id", name="pk_group_user_membership"),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_user_membership"),
    )

    op.create_index("ix_user_group_parent_id", "user_group", ["parent_id"])

    conn = op.get_bind()
    permission_row = conn.execute(
        sa.text("SELECT id FROM permission WHERE code = :code"),
        {"code": GROUP_MANAGE_CODE},
    ).first()
    if permission_row is None:
        conn.execute(
            sa.text("INSERT INTO permission (code) VALUES (:code)"),
            {"code": GROUP_MANAGE_CODE},
        )
        permission_row = conn.execute(
            sa.text("SELECT id FROM permission WHERE code = :code"),
            {"code": GROUP_MANAGE_CODE},
        ).first()

    if permission_row is not None:
        perm_id = permission_row[0]
        for role_name in DEFAULT_GROUP_ROLES:
            role_row = conn.execute(
                sa.text("SELECT id FROM role WHERE name = :name"),
                {"name": role_name},
            ).first()
            if not role_row:
                continue
            role_id = role_row[0]
            existing = conn.execute(
                sa.text(
                    "SELECT 1 FROM role_permissions WHERE role_id = :role_id AND perm_id = :perm_id"
                ),
                {"role_id": role_id, "perm_id": perm_id},
            ).first()
            if existing:
                continue
            conn.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, perm_id) VALUES (:role_id, :perm_id)"
                ),
                {"role_id": role_id, "perm_id": perm_id},
            )


def downgrade() -> None:
    op.drop_index("ix_user_group_parent_id", table_name="user_group")
    op.drop_table("group_user_membership")
    op.drop_table("user_group")
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE perm_id IN (SELECT id FROM permission WHERE code = :code)"
        ),
        {"code": GROUP_MANAGE_CODE},
    )
    conn.execute(
        sa.text("DELETE FROM permission WHERE code = :code"),
        {"code": GROUP_MANAGE_CODE},
    )
