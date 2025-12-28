from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "7d6e3f2a1b4c"
down_revision = "e6f1b2c3d4a5"
branch_labels = None
depends_on = None


PERMISSION_CODE = "service_account_api:manage"


def upgrade() -> None:
    conn = op.get_bind()

    perm_row = conn.execute(
        sa.text("SELECT id FROM permission WHERE code = :code"),
        {"code": PERMISSION_CODE},
    ).first()
    if perm_row is None:
        conn.execute(
            sa.text("INSERT INTO permission (code) VALUES (:code)"),
            {"code": PERMISSION_CODE},
        )
        perm_row = conn.execute(
            sa.text("SELECT id FROM permission WHERE code = :code"),
            {"code": PERMISSION_CODE},
        ).first()

    if not perm_row:
        return

    perm_id = perm_row[0]
    admin_role = conn.execute(
        sa.text("SELECT id FROM role WHERE name = 'admin'"),
    ).first()
    if not admin_role:
        return

    admin_role_id = admin_role[0]
    existing = conn.execute(
        sa.text(
            "SELECT 1 FROM role_permissions WHERE role_id = :role_id AND perm_id = :perm_id"
        ),
        {"role_id": admin_role_id, "perm_id": perm_id},
    ).first()
    if existing is None:
        conn.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, perm_id) VALUES (:role_id, :perm_id)"
            ),
            {"role_id": admin_role_id, "perm_id": perm_id},
        )


def downgrade() -> None:
    conn = op.get_bind()
    perm_row = conn.execute(
        sa.text("SELECT id FROM permission WHERE code = :code"),
        {"code": PERMISSION_CODE},
    ).first()
    if not perm_row:
        return

    perm_id = perm_row[0]
    conn.execute(
        sa.text("DELETE FROM role_permissions WHERE perm_id = :perm_id"),
        {"perm_id": perm_id},
    )
    conn.execute(
        sa.text("DELETE FROM permission WHERE id = :perm_id"),
        {"perm_id": perm_id},
    )
