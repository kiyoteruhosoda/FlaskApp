"""Local Import監査ログテーブル追加

Revision ID: add_local_import_audit_log
Revises: 
Create Date: 2025-12-28

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'add_local_import_audit_log'
down_revision = None  # TODO: 既存の最新revisionに設定してください
branch_labels = None
depends_on = None


def upgrade() -> None:
    """監査ログテーブルを作成"""
    
    # 監査ログテーブル（MariaDB用）
    op.create_table(
        'local_import_audit_log',
        
        # 主キー
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        
        # 基本情報
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('UTC_TIMESTAMP(6)')),
        sa.Column('level', sa.String(20), nullable=False, server_default='info'),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        
        # コンテキスト
        sa.Column('session_id', sa.BigInteger(), nullable=True),
        sa.Column('item_id', sa.String(255), nullable=True),
        sa.Column('request_id', sa.String(255), nullable=True),
        sa.Column('task_id', sa.String(255), nullable=True),
        sa.Column('user_id', sa.String(255), nullable=True),
        
        # 詳細データ（JSON）
        sa.Column('details', sa.JSON(), nullable=True),
        
        # エラー情報
        sa.Column('error_type', sa.String(255), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('stack_trace', sa.Text(), nullable=True),
        
        # 推奨アクション（JSON配列）
        sa.Column('recommended_actions', sa.JSON(), nullable=True),
        
        # パフォーマンス情報
        sa.Column('duration_ms', sa.Float(), nullable=True),
        
        # 状態遷移情報
        sa.Column('from_state', sa.String(50), nullable=True),
        sa.Column('to_state', sa.String(50), nullable=True),
        
        # 制約
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['session_id'], ['picker_session.id'], ondelete='CASCADE'),
    )
    
    # インデックス
    op.create_index('idx_timestamp', 'local_import_audit_log', ['timestamp'])
    op.create_index('idx_level', 'local_import_audit_log', ['level'])
    op.create_index('idx_category', 'local_import_audit_log', ['category'])
    op.create_index('idx_session_id', 'local_import_audit_log', ['session_id'])
    op.create_index('idx_item_id', 'local_import_audit_log', ['item_id'])
    op.create_index('idx_request_id', 'local_import_audit_log', ['request_id'])
    op.create_index('idx_task_id', 'local_import_audit_log', ['task_id'])
    op.create_index('idx_session_timestamp', 'local_import_audit_log', ['session_id', 'timestamp'])
    op.create_index('idx_item_timestamp', 'local_import_audit_log', ['item_id', 'timestamp'])
    op.create_index('idx_level_category', 'local_import_audit_log', ['level', 'category'])


def downgrade() -> None:
    """監査ログテーブルを削除"""
    op.drop_table('local_import_audit_log')
