"""Add media session permission"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a7d9c3e2b1f0'
down_revision = 'f3e2b1c4d5e6'
branch_labels = None
depends_on = None


PERMISSION_CODE = 'media:session'
ADMIN_ROLE_NAME = 'admin'


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

    conn.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, perm_id)
            SELECT r.id, :perm_id
            FROM role r
            WHERE r.name = :role_name
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.id AND rp.perm_id = :perm_id
              )
            """
        ),
        {"perm_id": perm_id, "role_name": ADMIN_ROLE_NAME},
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
