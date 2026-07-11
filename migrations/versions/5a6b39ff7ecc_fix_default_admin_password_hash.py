"""fix default admin password hash

``shared/domain/auth/master_data.py`` の ``DEFAULT_ADMIN_PASSWORD_HASH``
（および ``2a1f9c0b3d4e_seed_master_data`` が投入したフォールバックハッシュ）は、
コメント・ドキュメント上は平文 "admin" のハッシュだと説明されていたが、実際には
平文 "admin@example.com"（初期管理者のメールアドレス）のハッシュだった。
そのため ``ADMIN_INITIAL_PASSWORD`` 未指定でデプロイした環境では、案内どおりの
"admin@example.com" / "admin" ではログインできなかった（401 invalid_credentials）。

このマイグレーションは、初期管理者ユーザーの ``password_hash`` が旧・誤ハッシュの
ままの行だけを補正する（本人が既にパスワードを変更済みの行には触れない）。

Revision ID: 5a6b39ff7ecc
Revises: 2a1f9c0b3d4e
Create Date: 2026-07-11

"""
from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa

from shared.domain.auth.master_data import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD_HASH,
)

# revision identifiers, used by Alembic.
revision = "5a6b39ff7ecc"
down_revision = "2a1f9c0b3d4e"
branch_labels = None
depends_on = None

# 修正前に投入されていた誤ハッシュ（平文 "admin" ではなく "admin@example.com" のハッシュ）。
LEGACY_BROKEN_ADMIN_PASSWORD_HASH = (
    "scrypt:32768:8:1$7oTcIUdekNLXGSXC$"
    "fd0f3320bde4570c7e1ea9d9d289aeb916db7a50fb62489a7e89d99c6cc576813506fd99"
    "f50904101c1eb85ff925f8dc879df5ded781ef2613224d702938c9c8"
)


def _resolve_admin_password_hash() -> str:
    """環境変数があれば平文をハッシュ化し、無ければ修正後のフォールバックを返す。"""

    raw = os.environ.get("ADMIN_INITIAL_PASSWORD")
    if raw:
        from werkzeug.security import generate_password_hash

        return generate_password_hash(raw)
    return DEFAULT_ADMIN_PASSWORD_HASH


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            "UPDATE user SET password_hash = :new_hash "
            "WHERE email = :email AND password_hash = :old_hash"
        ),
        {
            "new_hash": _resolve_admin_password_hash(),
            "email": DEFAULT_ADMIN_EMAIL,
            "old_hash": LEGACY_BROKEN_ADMIN_PASSWORD_HASH,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()

    # ADMIN_INITIAL_PASSWORD 経由で設定された値は復元できないため、
    # デフォルトのフォールバックハッシュだった行だけを旧ハッシュへ戻す。
    conn.execute(
        sa.text(
            "UPDATE user SET password_hash = :old_hash "
            "WHERE email = :email AND password_hash = :new_hash"
        ),
        {
            "old_hash": LEGACY_BROKEN_ADMIN_PASSWORD_HASH,
            "email": DEFAULT_ADMIN_EMAIL,
            "new_hash": DEFAULT_ADMIN_PASSWORD_HASH,
        },
    )
