"""add media duplicate lookup indexes

ローカルインポートの重複判定（``find_by_signature`` / ``exists_by_hash``）と
原本再構築（``rebuild_media_from_originals``）は ``media.hash_sha256`` /
``media.phash`` / ``media.local_rel_path`` で検索するが、これらの列には
インデックスが無く、取り込みファイル1件ごとに ``media`` テーブルの
フルスキャンが発生していた（ライブラリ N 件 × 取り込み M 件で O(N×M)）。

検索パターンに合わせたインデックスを追加する。

レガシーDB（Alembic管理外で現行モデルからスキーマ構築済み）は
``run_db_migrations.py`` が ``init_master`` へ stamp してから upgrade head で
本マイグレーションを再生するため、インデックスが既に存在しても失敗しない
よう ``if_not_exists`` / ``if_exists`` を指定する。

Revision ID: b7d41c2f9a10
Revises: 0900277b3348
Create Date: 2026-07-19

"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "b7d41c2f9a10"
down_revision = "0900277b3348"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_media_hash_sha256_bytes",
        "media",
        ["hash_sha256", "bytes"],
        if_not_exists=True,
    )
    op.create_index("ix_media_phash", "media", ["phash"], if_not_exists=True)
    op.create_index(
        "ix_media_local_rel_path", "media", ["local_rel_path"], if_not_exists=True
    )


def downgrade() -> None:
    op.drop_index("ix_media_local_rel_path", table_name="media", if_exists=True)
    op.drop_index("ix_media_phash", table_name="media", if_exists=True)
    op.drop_index("ix_media_hash_sha256_bytes", table_name="media", if_exists=True)
