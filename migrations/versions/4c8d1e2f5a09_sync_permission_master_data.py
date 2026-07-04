"""sync permission master data (add missing codes / role grants)

``admin:system-settings`` と ``media:session`` が API・画面で要求されて
いるにもかかわらず権限マスタに存在せず、admin を含むどのロールにも
付与できない状態だったため、``shared.domain.auth.master_data`` を唯一の
出所として不足分の権限コードとロールへの付与を冪等に同期する。

seed（2a1f9c0b3d4e）適用済みの既存 DB に対する追い付き用データ
マイグレーション。新規 DB では seed が同じ master_data を読むため
本マイグレーションは実質 no-op となる。

Revision ID: 4c8d1e2f5a09
Revises: 3b7c2e9a1f08
Create Date: 2026-07-04

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from shared.domain.auth.master_data import PERMISSION_CODES, ROLE_PERMISSIONS

# revision identifiers, used by Alembic.
revision = "4c8d1e2f5a09"
down_revision = "3b7c2e9a1f08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # --- 不足している権限コードを追加（code を安定キーに冪等挿入）------------
    for code in PERMISSION_CODES:
        exists = conn.execute(
            sa.text("SELECT 1 FROM permission WHERE code = :code"), {"code": code}
        ).first()
        if not exists:
            conn.execute(
                sa.text("INSERT INTO permission (code) VALUES (:code)"),
                {"code": code},
            )

    # --- 不足しているロールへの権限付与を追加 --------------------------------
    for role_name, codes in ROLE_PERMISSIONS.items():
        role_row = conn.execute(
            sa.text("SELECT id FROM role WHERE name = :name"), {"name": role_name}
        ).first()
        if not role_row:
            continue
        role_id = role_row[0]
        for code in codes:
            perm_row = conn.execute(
                sa.text("SELECT id FROM permission WHERE code = :code"),
                {"code": code},
            ).first()
            if not perm_row:
                continue
            perm_id = perm_row[0]
            linked = conn.execute(
                sa.text(
                    "SELECT 1 FROM role_permissions "
                    "WHERE role_id = :role_id AND perm_id = :perm_id"
                ),
                {"role_id": role_id, "perm_id": perm_id},
            ).first()
            if not linked:
                conn.execute(
                    sa.text(
                        "INSERT INTO role_permissions (role_id, perm_id) "
                        "VALUES (:role_id, :perm_id)"
                    ),
                    {"role_id": role_id, "perm_id": perm_id},
                )


def downgrade() -> None:
    # 追加同期のみのデータマイグレーションのため downgrade は no-op とする。
    # どのコードが本マイグレーションで追加されたかは適用時の DB 状態に依存し、
    # 一律削除すると運用中に作成されたカスタムロールの付与を壊すため削除しない。
    pass
