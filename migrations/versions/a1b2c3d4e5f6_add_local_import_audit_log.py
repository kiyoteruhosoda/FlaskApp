"""add local_import_audit_log table

Revision ID: a1b2c3d4e5f6
Revises: 
Create Date: 2024-12-28 10:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'a4e3d9f2c5ab'
branch_labels = None
depends_on = None


def upgrade():
    """local_import_audit_logテーブルを作成"""
    
    # MariaDB互換: String型を使用（Enum禁止）
    op.create_table(
        'local_import_audit_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=False), nullable=False, server_default=sa.text('UTC_TIMESTAMP(6)')),
        sa.Column('level', sa.String(20), nullable=False),  # DEBUG, INFO, WARNING, ERROR
        sa.Column('category', sa.String(50), nullable=False),  # state_transition, file_operation, etc.
        sa.Column('message', sa.Text(), nullable=False),
        
        # 関連ID
        sa.Column('session_id', sa.BigInteger(), nullable=True),
        sa.Column('item_id', sa.String(255), nullable=True),
        
        # 追跡ID
        sa.Column('request_id', sa.String(255), nullable=True),
        sa.Column('task_id', sa.String(255), nullable=True),
        sa.Column('correlation_id', sa.String(255), nullable=True),
        
        # 詳細情報（JSON）
        sa.Column('details', sa.JSON(), nullable=True),
        
        # エラー情報
        sa.Column('error_type', sa.String(255), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('stack_trace', sa.Text(), nullable=True),
        sa.Column('recommended_actions', sa.JSON(), nullable=True),
        
        # パフォーマンス情報
        sa.Column('duration_ms', sa.Float(), nullable=True),
        
        # 状態遷移情報
        sa.Column('from_state', sa.String(50), nullable=True),
        sa.Column('to_state', sa.String(50), nullable=True),
        
        sa.PrimaryKeyConstraint('id'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
        mysql_engine='InnoDB'
    )
    
    # インデックス作成（パフォーマンス最適化）
    op.create_index('idx_timestamp', 'local_import_audit_log', ['timestamp'])
    op.create_index('idx_level', 'local_import_audit_log', ['level'])
    op.create_index('idx_category', 'local_import_audit_log', ['category'])
    op.create_index('idx_session_id', 'local_import_audit_log', ['session_id'])
    op.create_index('idx_item_id', 'local_import_audit_log', ['item_id'])
    op.create_index('idx_request_id', 'local_import_audit_log', ['request_id'])
    op.create_index('idx_task_id', 'local_import_audit_log', ['task_id'])
    
    # 複合インデックス（よく使うクエリ用）
    op.create_index('idx_session_timestamp', 'local_import_audit_log', ['session_id', 'timestamp'])
    op.create_index('idx_item_timestamp', 'local_import_audit_log', ['item_id', 'timestamp'])
    op.create_index('idx_level_category', 'local_import_audit_log', ['level', 'category'])


def downgrade():
    """local_import_audit_logテーブルを削除"""
    
    # インデックス削除
    op.drop_index('idx_level_category', table_name='local_import_audit_log')
    op.drop_index('idx_item_timestamp', table_name='local_import_audit_log')
    op.drop_index('idx_session_timestamp', table_name='local_import_audit_log')
    op.drop_index('idx_task_id', table_name='local_import_audit_log')
    op.drop_index('idx_request_id', table_name='local_import_audit_log')
    op.drop_index('idx_item_id', table_name='local_import_audit_log')
    op.drop_index('idx_session_id', table_name='local_import_audit_log')
    op.drop_index('idx_category', table_name='local_import_audit_log')
    op.drop_index('idx_level', table_name='local_import_audit_log')
    op.drop_index('idx_timestamp', table_name='local_import_audit_log')
    
    # テーブル削除
    op.drop_table('local_import_audit_log')
