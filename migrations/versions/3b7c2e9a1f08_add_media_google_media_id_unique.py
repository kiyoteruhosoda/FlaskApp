"""add unique constraint on media.google_media_id

Google Photos 取り込みの冪等性を DB レベルで担保するため、
``media.google_media_id`` に一意制約を追加する。NULL（ローカル取り込み）は
MariaDB/SQLite とも複数許容されるため、ローカルメディアには影響しない。

注: 既存 DB に google_media_id の重複行がある場合、本マイグレーションは失敗する。
その場合は事前に重複を解消（統合またはソフト削除側の物理削除）すること。
取り込みコードは再取り込み時に既存行を「復活＋更新」する方式に変更済みのため、
今後の重複混入は発生しない。

Revision ID: 3b7c2e9a1f08
Revises: 2a1f9c0b3d4e
Create Date: 2026-06-28

"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "3b7c2e9a1f08"
down_revision = "2a1f9c0b3d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("media", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_media_google_media_id", ["google_media_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("media", schema=None) as batch_op:
        batch_op.drop_constraint("uq_media_google_media_id", type_="unique")
