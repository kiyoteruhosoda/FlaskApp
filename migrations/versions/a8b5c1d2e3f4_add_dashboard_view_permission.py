from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a8b5c1d2e3f4'
down_revision = 'f3e2b1c4d5e6'
branch_labels = None
depends_on = None

PERMISSION_CODE = 'dashboard:view'
ROLE_NAMES = ('admin', 'manager', 'member', 'guest')


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

    for role_name in ROLE_NAMES:
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
