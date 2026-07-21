"""change default admin password to the admin email address

``shared/domain/auth/master_data.py`` の ``DEFAULT_ADMIN_PASSWORD_HASH``
（``ADMIN_INITIAL_PASSWORD`` 未指定時のフォールバック）を、平文 "admin" の
ハッシュから平文 "admin@example.com"（初期管理者のメールアドレスと同じ）の
ハッシュへ変更した。これに合わせて、既存の初期管理者ユーザーの
``password_hash`` が旧フォールバック（平文 "admin"）のままの行だけを補正する
（本人が既にパスワードを変更済みの行や、``ADMIN_INITIAL_PASSWORD`` 経由で
別値を設定した行には触れない）。

Revision ID: e2f4a7c9d305
Revises: b7d41c2f9a10
Create Date: 2026-07-21

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
revision = "e2f4a7c9d305"
down_revision = "b7d41c2f9a10"
branch_labels = None
depends_on = None

# 変更前のフォールバックハッシュ（平文 "admin"）。この値のままの行だけを補正する。
LEGACY_ADMIN_PASSWORD_HASH = (
    "scrypt:32768:8:1$kp58BgWIX2eGuqc6$"
    "879463f4b7684251a26d3ce6d863de80b756a47c42244709a752e0b935ad5f0b7392f598"
    "b9a43436d8af47aba78d78c726eb8fab983fe03e823c19f92108ff27"
)


def _resolve_admin_password_hash() -> str:
    """環境変数があれば平文をハッシュ化し、無ければ変更後のフォールバックを返す。"""

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
            "old_hash": LEGACY_ADMIN_PASSWORD_HASH,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()

    # ADMIN_INITIAL_PASSWORD 経由で設定された値は復元できないため、
    # 変更後のデフォルトのフォールバックハッシュだった行だけを旧ハッシュへ戻す。
    conn.execute(
        sa.text(
            "UPDATE user SET password_hash = :old_hash "
            "WHERE email = :email AND password_hash = :new_hash"
        ),
        {
            "old_hash": LEGACY_ADMIN_PASSWORD_HASH,
            "email": DEFAULT_ADMIN_EMAIL,
            "new_hash": DEFAULT_ADMIN_PASSWORD_HASH,
        },
    )
