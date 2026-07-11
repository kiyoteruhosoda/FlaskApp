"""sync role permissions with master data

``shared/domain/auth/master_data.py`` の ``PERMISSION_CODES`` /
``ROLE_PERMISSIONS`` は開発の過程で権限コードが追加されてきたが、投入は
``2a1f9c0b3d4e_seed_master_data`` が一度だけ実行するデータマイグレーション
であり、それより後に追加された権限コードは既存DBの ``permission`` /
``role_permissions`` テーブルへ自動的には反映されない。

その結果、初期管理者（``admin`` ロール = マスタデータ上は「全権限」の
はず）でログインしても、後から追加された権限コードが要求される画面
（Wiki管理・成り代わり等）で「権限がありません」と表示される実害があった。

このマイグレーションは、現時点の ``PERMISSION_CODES`` / ``ROLE_PERMISSIONS``
を唯一の出所として、不足している権限コード・ロールへの権限付与だけを
差分投入する（既存の付与を削除しない・冪等）。

Revision ID: 0900277b3348
Revises: 5a6b39ff7ecc
Create Date: 2026-07-11

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from shared.domain.auth.master_data import PERMISSION_CODES, ROLE_PERMISSIONS

# revision identifiers, used by Alembic.
revision = "0900277b3348"
down_revision = "5a6b39ff7ecc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # --- 不足している権限コードを追加 ---------------------------------------
    for code in PERMISSION_CODES:
        exists = conn.execute(
            sa.text("SELECT 1 FROM permission WHERE code = :code"), {"code": code}
        ).first()
        if not exists:
            conn.execute(
                sa.text("INSERT INTO permission (code) VALUES (:code)"),
                {"code": code},
            )

    # --- ロールへの権限付与の不足分を追加 -----------------------------------
    for role_name, codes in ROLE_PERMISSIONS.items():
        role_row = conn.execute(
            sa.text("SELECT id FROM role WHERE name = :name"), {"name": role_name}
        ).first()
        if not role_row:
            continue
        role_id = role_row[0]
        for code in codes:
            perm_row = conn.execute(
                sa.text("SELECT id FROM permission WHERE code = :code"), {"code": code}
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
    # 差分投入のみのマイグレーションであり、どの行が本マイグレーション由来か
    # 判別できないため、安全に取り消す方法がない（他の正当な権限付与を誤って
    # 削除するリスクがある）。意図的に no-op とする。
    pass
