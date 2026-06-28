"""init master schema (consolidated baseline)

現状の SQLAlchemy モデル定義（target_metadata）から機械生成した、
全テーブルを一括作成する単一のベースライン・マイグレーション。

このリビジョンはアプリケーションの「正しい現行スキーマ」を表す。
ロール・権限・管理者ユーザー等のマスタデータは本マイグレーションには
含めず、``python scripts/seed_master_data.py`` で投入する（冪等）。

Revision ID: init_master
Revises:
Create Date: 2026-06-28

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "init_master"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('celery_task',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('task_name', sa.String(length=255), nullable=False),
    sa.Column('object_type', sa.String(length=64), nullable=True),
    sa.Column('object_id', sa.String(length=255), nullable=True),
    sa.Column('celery_task_id', sa.String(length=255), nullable=True),
    sa.Column('status', sa.Enum('scheduled', 'queued', 'running', 'success', 'failed', 'canceled', name='celery_task_status'), server_default='queued', nullable=False),
    sa.Column('scheduled_for', sa.DateTime(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('payload_json', sa.Text(), server_default='{}', nullable=False),
    sa.Column('result_json', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('celery_task_id')
    )
    op.create_index('ix_celery_task_object', 'celery_task', ['object_type', 'object_id'], unique=False)
    op.create_index('ix_celery_task_task_name_status', 'celery_task', ['task_name', 'status'], unique=False)
    op.create_table('certificate_events',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('actor', sa.String(length=255), nullable=False),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('target_kid', sa.String(length=64), nullable=True),
    sa.Column('target_group_code', sa.String(length=64), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('details', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('occurred_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_certificate_events_occurred_at'), 'certificate_events', ['occurred_at'], unique=False)
    op.create_index(op.f('ix_certificate_events_target_group_code'), 'certificate_events', ['target_group_code'], unique=False)
    op.create_index(op.f('ix_certificate_events_target_kid'), 'certificate_events', ['target_kid'], unique=False)
    op.create_table('certificate_groups',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('group_code', sa.String(length=64), nullable=False),
    sa.Column('display_name', sa.String(length=128), nullable=True),
    sa.Column('auto_rotate', sa.Boolean(), nullable=False),
    sa.Column('rotation_threshold_days', sa.Integer(), nullable=False),
    sa.Column('key_type', sa.String(length=16), nullable=False),
    sa.Column('key_curve', sa.String(length=32), nullable=True),
    sa.Column('key_size', sa.Integer(), nullable=True),
    sa.Column('subject', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('usage_type', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('group_code')
    )
    op.create_index(op.f('ix_certificate_groups_usage_type'), 'certificate_groups', ['usage_type'], unique=False)
    op.create_table('log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('level', sa.String(length=50), nullable=False),
    sa.Column('event', sa.String(length=50), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('trace', sa.Text(), nullable=True),
    sa.Column('path', sa.String(length=255), nullable=True),
    sa.Column('request_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('password_reset_token',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('token_hash', sa.String(length=255), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index(op.f('ix_password_reset_token_email'), 'password_reset_token', ['email'], unique=False)
    op.create_table('permission',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=120), nullable=False),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('photo_metadata',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('focal_length', sa.Float(), nullable=True),
    sa.Column('aperture_f_number', sa.Float(), nullable=True),
    sa.Column('iso_equivalent', sa.Integer(), nullable=True),
    sa.Column('exposure_time', sa.String(length=32), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('picker_import_task',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('role',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('system_settings',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('setting_key', sa.String(length=100), nullable=False),
    sa.Column('setting_json', sa.JSON(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('setting_key'),
    sqlite_autoincrement=True
    )
    op.create_table('user',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('username', sa.String(length=80), nullable=True),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('totp_secret', sa.String(length=32), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('refresh_token_hash', sa.String(length=255), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_email'), 'user', ['email'], unique=True)
    op.create_table('user_group',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('parent_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.ForeignKeyConstraint(['parent_id'], ['user_group.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name', name='uq_user_group_name')
    )
    op.create_table('video_metadata',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('fps', sa.Float(), nullable=True),
    sa.Column('processing_status', sa.Enum('UNSPECIFIED', 'PROCESSING', 'READY', 'FAILED', name='video_processing_status'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('wiki_category',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('slug', sa.String(length=100), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_wiki_category_slug'), 'wiki_category', ['slug'], unique=True)
    op.create_table('worker_log',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('level', sa.String(length=20), nullable=False),
    sa.Column('event', sa.String(length=50), nullable=False),
    sa.Column('logger_name', sa.String(length=120), nullable=True),
    sa.Column('task_name', sa.String(length=255), nullable=True),
    sa.Column('task_uuid', sa.String(length=36), nullable=True),
    sa.Column('file_task_id', sa.String(length=64), nullable=True),
    sa.Column('progress_step', sa.Integer(), nullable=True),
    sa.Column('worker_hostname', sa.String(length=255), nullable=True),
    sa.Column('queue_name', sa.String(length=120), nullable=True),
    sa.Column('status', sa.String(length=40), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('trace', sa.Text(), nullable=True),
    sa.Column('meta_json', sa.JSON(), nullable=True),
    sa.Column('extra_json', sa.JSON(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_worker_log_event', 'worker_log', ['event'], unique=False)
    op.create_index('ix_worker_log_file_task_id', 'worker_log', ['file_task_id'], unique=False)
    op.create_index('ix_worker_log_file_task_id_progress_step', 'worker_log', ['file_task_id', 'progress_step'], unique=False)
    op.create_table('google_account',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('scopes', sa.Text(), nullable=False),
    sa.Column('last_synced_at', sa.DateTime(), nullable=True),
    sa.Column('oauth_token_json', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'email', name='uq_user_google_email')
    )
    op.create_table('group_user_membership',
    sa.Column('group_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.ForeignKeyConstraint(['group_id'], ['user_group.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('group_id', 'user_id'),
    sa.UniqueConstraint('group_id', 'user_id', name='uq_group_user_membership')
    )
    op.create_table('issued_certificates',
    sa.Column('kid', sa.String(length=64), nullable=False),
    sa.Column('usage_type', sa.String(length=32), nullable=False),
    sa.Column('group_id', sa.BigInteger(), nullable=True),
    sa.Column('certificate_pem', sa.Text(), nullable=False),
    sa.Column('jwk', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('issued_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.Column('revocation_reason', sa.Text(), nullable=True),
    sa.Column('auto_rotated_from_kid', sa.String(length=64), nullable=True),
    sa.ForeignKeyConstraint(['group_id'], ['certificate_groups.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('kid')
    )
    op.create_index(op.f('ix_issued_certificates_expires_at'), 'issued_certificates', ['expires_at'], unique=False)
    op.create_index(op.f('ix_issued_certificates_issued_at'), 'issued_certificates', ['issued_at'], unique=False)
    op.create_index(op.f('ix_issued_certificates_usage_type'), 'issued_certificates', ['usage_type'], unique=False)
    op.create_table('media_item',
    sa.Column('id', sa.String(length=255), nullable=False),
    sa.Column('type', sa.Enum('TYPE_UNSPECIFIED', 'PHOTO', 'VIDEO', name='media_item_type'), nullable=False),
    sa.Column('mime_type', sa.String(length=255), nullable=True),
    sa.Column('filename', sa.String(length=255), nullable=True),
    sa.Column('width', sa.Integer(), nullable=True),
    sa.Column('height', sa.Integer(), nullable=True),
    sa.Column('camera_make', sa.String(length=255), nullable=True),
    sa.Column('camera_model', sa.String(length=255), nullable=True),
    sa.Column('photo_metadata_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('video_metadata_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['photo_metadata_id'], ['photo_metadata.id'], ),
    sa.ForeignKeyConstraint(['video_metadata_id'], ['video_metadata.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('passkey_credential',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('credential_id', sa.String(length=255), nullable=False),
    sa.Column('public_key', sa.Text(), nullable=False),
    sa.Column('sign_count', sa.BigInteger(), nullable=False),
    sa.Column('transports', sa.JSON(), nullable=True),
    sa.Column('name', sa.String(length=255), nullable=True),
    sa.Column('attestation_format', sa.String(length=64), nullable=True),
    sa.Column('aaguid', sa.String(length=64), nullable=True),
    sa.Column('backup_eligible', sa.Boolean(), nullable=False),
    sa.Column('backup_state', sa.Boolean(), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('credential_id', name='uq_passkey_credential_id')
    )
    op.create_index(op.f('ix_passkey_credential_user_id'), 'passkey_credential', ['user_id'], unique=False)
    op.create_table('role_permissions',
    sa.Column('role_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('perm_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.ForeignKeyConstraint(['perm_id'], ['permission.id'], ),
    sa.ForeignKeyConstraint(['role_id'], ['role.id'], ),
    sa.PrimaryKeyConstraint('role_id', 'perm_id')
    )
    op.create_table('service_account',
    sa.Column('service_account_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('certificate_group_code', sa.String(length=64), nullable=True),
    sa.Column('scope_names', sa.String(length=1000), nullable=False),
    sa.Column('active_flg', sa.Boolean(), nullable=False),
    sa.Column('reg_dttm', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('mod_dttm', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['certificate_group_code'], ['certificate_groups.group_code'], ),
    sa.PrimaryKeyConstraint('service_account_id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('tag',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('attr', sa.Enum('thing', 'person', 'place', 'event', 'scene', 'activity', 'source', 'others', name='tag_attr'), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('totp_credential',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('account', sa.String(length=255), nullable=False),
    sa.Column('issuer', sa.String(length=255), nullable=False),
    sa.Column('secret', sa.String(length=160), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('algorithm', sa.String(length=16), nullable=False),
    sa.Column('digits', sa.SmallInteger(), nullable=False),
    sa.Column('period', sa.SmallInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'account', 'issuer', name='uq_totp_user_account_issuer')
    )
    op.create_index(op.f('ix_totp_credential_user_id'), 'totp_credential', ['user_id'], unique=False)
    op.create_table('user_roles',
    sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('role_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['role.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'role_id')
    )
    op.create_table('wiki_page',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('slug', sa.String(length=255), nullable=False),
    sa.Column('is_published', sa.Boolean(), nullable=False),
    sa.Column('parent_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('updated_by_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['parent_id'], ['wiki_page.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_wiki_page_slug'), 'wiki_page', ['slug'], unique=True)
    op.create_table('certificate_private_keys',
    sa.Column('kid', sa.String(length=64), nullable=False),
    sa.Column('group_id', sa.BigInteger(), nullable=True),
    sa.Column('private_key_pem', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['group_id'], ['certificate_groups.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['kid'], ['issued_certificates.kid'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('kid')
    )
    op.create_index(op.f('ix_certificate_private_keys_created_at'), 'certificate_private_keys', ['created_at'], unique=False)
    op.create_index(op.f('ix_certificate_private_keys_expires_at'), 'certificate_private_keys', ['expires_at'], unique=False)
    op.create_table('media',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('source_type', sa.Enum('local', 'google_photos', 'wiki-media', name='media_source_type'), nullable=False),
    sa.Column('google_media_id', sa.String(length=255), nullable=True),
    sa.Column('account_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('local_rel_path', sa.String(length=255), nullable=True),
    sa.Column('thumbnail_rel_path', sa.String(length=255), nullable=True),
    sa.Column('filename', sa.String(length=255), nullable=True),
    sa.Column('hash_sha256', sa.CHAR(length=64), nullable=True),
    sa.Column('phash', sa.String(length=64), nullable=True),
    sa.Column('bytes', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('mime_type', sa.String(length=255), nullable=True),
    sa.Column('width', sa.Integer(), nullable=True),
    sa.Column('height', sa.Integer(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('orientation', sa.Integer(), nullable=True),
    sa.Column('is_video', sa.Boolean(), nullable=False),
    sa.Column('shot_at', sa.DateTime(), nullable=True),
    sa.Column('camera_make', sa.String(length=255), nullable=True),
    sa.Column('camera_model', sa.String(length=255), nullable=True),
    sa.Column('imported_at', sa.DateTime(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('has_playback', sa.Boolean(), nullable=False),
    sa.Column('live_group_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['google_account.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('picker_session',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('account_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('session_id', sa.String(length=255), nullable=True),
    sa.Column('picker_uri', sa.Text(), nullable=True),
    sa.Column('expire_time', sa.DateTime(), nullable=True),
    sa.Column('polling_config_json', sa.Text(), nullable=True),
    sa.Column('picking_config_json', sa.Text(), nullable=True),
    sa.Column('media_items_set', sa.Boolean(), nullable=True),
    sa.Column('status', sa.Enum('pending', 'ready', 'expanding', 'processing', 'enqueued', 'importing', 'imported', 'canceled', 'expired', 'error', 'failed', name='picker_session_status'), server_default='pending', nullable=False),
    sa.Column('selected_count', sa.Integer(), nullable=True),
    sa.Column('stats_json', sa.Text(), nullable=True),
    sa.Column('last_polled_at', sa.DateTime(), nullable=True),
    sa.Column('last_progress_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['google_account.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('session_id')
    )
    op.create_table('service_account_api_key',
    sa.Column('api_key_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('service_account_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('public_id', sa.String(length=32), nullable=False),
    sa.Column('secret_hash', sa.String(length=255), nullable=False),
    sa.Column('scope_names', sa.String(length=2000), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by', sa.String(length=255), nullable=False),
    sa.ForeignKeyConstraint(['service_account_id'], ['service_account.service_account_id'], ),
    sa.PrimaryKeyConstraint('api_key_id'),
    sa.UniqueConstraint('public_id')
    )
    op.create_index(op.f('ix_service_account_api_key_service_account_id'), 'service_account_api_key', ['service_account_id'], unique=False)
    op.create_table('wiki_page_category',
    sa.Column('page_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('category_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['wiki_category.id'], ),
    sa.ForeignKeyConstraint(['page_id'], ['wiki_page.id'], ),
    sa.PrimaryKeyConstraint('page_id', 'category_id')
    )
    op.create_table('wiki_revision',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('page_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('revision_number', sa.Integer(), nullable=False),
    sa.Column('change_summary', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_by_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['page_id'], ['wiki_page.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('album',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('cover_media_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('visibility', sa.Enum('public', 'private', 'unlisted', name='album_visibility'), nullable=False),
    sa.Column('display_order', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['cover_media_id'], ['media.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('exif',
    sa.Column('media_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('camera_make', sa.String(length=255), nullable=True),
    sa.Column('camera_model', sa.String(length=255), nullable=True),
    sa.Column('lens', sa.String(length=255), nullable=True),
    sa.Column('iso', sa.Integer(), nullable=True),
    sa.Column('shutter', sa.String(length=32), nullable=True),
    sa.Column('f_number', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('focal_len', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('gps_lat', sa.Numeric(precision=10, scale=7), nullable=True),
    sa.Column('gps_lng', sa.Numeric(precision=10, scale=7), nullable=True),
    sa.Column('raw_json', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['media_id'], ['media.id'], ),
    sa.PrimaryKeyConstraint('media_id')
    )
    op.create_table('job_sync',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('target', sa.String(length=50), nullable=False),
    sa.Column('task_name', sa.String(length=255), server_default='', nullable=False),
    sa.Column('queue_name', sa.String(length=120), nullable=True),
    sa.Column('trigger', sa.String(length=32), server_default='worker', nullable=False),
    sa.Column('account_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('session_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('celery_task_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('status', sa.Enum('queued', 'running', 'success', 'partial', 'failed', 'canceled', name='job_sync_status'), server_default='queued', nullable=False),
    sa.Column('args_json', sa.Text(), server_default='{}', nullable=False),
    sa.Column('stats_json', sa.Text(), server_default='{}', nullable=False),
    sa.ForeignKeyConstraint(['celery_task_id'], ['celery_task.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['picker_session.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('local_import_audit_log',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('level', sa.Enum('debug', 'info', 'warning', 'error', 'critical', name='audit_log_level'), nullable=False),
    sa.Column('category', sa.Enum('state_transition', 'file_operation', 'db_operation', 'validation', 'duplicate_check', 'error', 'performance', 'consistency', name='audit_log_category'), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('session_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.Column('item_id', sa.String(length=255), nullable=True),
    sa.Column('request_id', sa.String(length=255), nullable=True),
    sa.Column('task_id', sa.String(length=255), nullable=True),
    sa.Column('user_id', sa.String(length=255), nullable=True),
    sa.Column('details', sa.JSON(), nullable=True),
    sa.Column('error_type', sa.String(length=255), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('stack_trace', sa.Text(), nullable=True),
    sa.Column('recommended_actions', sa.JSON(), nullable=True),
    sa.Column('duration_ms', sa.Float(), nullable=True),
    sa.Column('from_state', sa.String(length=50), nullable=True),
    sa.Column('to_state', sa.String(length=50), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['picker_session.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_item_timestamp', 'local_import_audit_log', ['item_id', 'timestamp'], unique=False)
    op.create_index('idx_level_category', 'local_import_audit_log', ['level', 'category'], unique=False)
    op.create_index('idx_session_timestamp', 'local_import_audit_log', ['session_id', 'timestamp'], unique=False)
    op.create_index(op.f('ix_local_import_audit_log_category'), 'local_import_audit_log', ['category'], unique=False)
    op.create_index(op.f('ix_local_import_audit_log_item_id'), 'local_import_audit_log', ['item_id'], unique=False)
    op.create_index(op.f('ix_local_import_audit_log_level'), 'local_import_audit_log', ['level'], unique=False)
    op.create_index(op.f('ix_local_import_audit_log_request_id'), 'local_import_audit_log', ['request_id'], unique=False)
    op.create_index(op.f('ix_local_import_audit_log_session_id'), 'local_import_audit_log', ['session_id'], unique=False)
    op.create_index(op.f('ix_local_import_audit_log_task_id'), 'local_import_audit_log', ['task_id'], unique=False)
    op.create_index(op.f('ix_local_import_audit_log_timestamp'), 'local_import_audit_log', ['timestamp'], unique=False)
    op.create_table('media_playback',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('media_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('preset', sa.Enum('original', 'preview', 'mobile', 'std1080p', name='media_playback_preset'), nullable=False),
    sa.Column('rel_path', sa.String(length=255), nullable=True),
    sa.Column('width', sa.Integer(), nullable=True),
    sa.Column('height', sa.Integer(), nullable=True),
    sa.Column('v_codec', sa.String(length=32), nullable=True),
    sa.Column('a_codec', sa.String(length=32), nullable=True),
    sa.Column('v_bitrate_kbps', sa.Integer(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('poster_rel_path', sa.String(length=255), nullable=True),
    sa.Column('hash_sha256', sa.CHAR(length=64), nullable=True),
    sa.Column('status', sa.Enum('pending', 'processing', 'done', 'error', name='media_playback_status'), nullable=False),
    sa.Column('error_msg', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['media_id'], ['media.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('media_sidecar',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('media_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('type', sa.Enum('video', 'audio', 'subtitle', name='media_sidecar_type'), nullable=False),
    sa.Column('rel_path', sa.String(length=255), nullable=True),
    sa.Column('bytes', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.ForeignKeyConstraint(['media_id'], ['media.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('media_tag',
    sa.Column('media_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('tag_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.ForeignKeyConstraint(['media_id'], ['media.id'], ),
    sa.ForeignKeyConstraint(['tag_id'], ['tag.id'], ),
    sa.PrimaryKeyConstraint('media_id', 'tag_id')
    )
    op.create_table('picker_selection',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('google_media_id', sa.String(length=255), nullable=True),
    sa.Column('local_file_path', sa.Text(), nullable=True),
    sa.Column('local_filename', sa.String(length=500), nullable=True),
    sa.Column('status', sa.Enum('pending', 'enqueued', 'running', 'imported', 'dup', 'failed', 'expired', 'skipped', name='picker_selection_status'), server_default='pending', nullable=False),
    sa.Column('create_time', sa.DateTime(), nullable=True),
    sa.Column('enqueued_at', sa.DateTime(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('error_msg', sa.Text(), nullable=True),
    sa.Column('base_url', sa.Text(), nullable=True),
    sa.Column('base_url_fetched_at', sa.DateTime(), nullable=True),
    sa.Column('base_url_valid_until', sa.DateTime(), nullable=True),
    sa.Column('locked_by', sa.String(length=255), nullable=True),
    sa.Column('lock_heartbeat_at', sa.DateTime(), nullable=True),
    sa.Column('last_transition_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['google_media_id'], ['media_item.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['picker_session.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('session_id', 'google_media_id', name='uq_picker_selection_session_media')
    )
    op.create_index('idx_picker_selection_session_status', 'picker_selection', ['session_id', 'status'], unique=False)
    op.create_index('idx_picker_selection_status_lock', 'picker_selection', ['status', 'lock_heartbeat_at'], unique=False)
    op.create_table('service_account_api_key_log',
    sa.Column('log_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('api_key_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('accessed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('endpoint', sa.String(length=255), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['api_key_id'], ['service_account_api_key.api_key_id'], ),
    sa.PrimaryKeyConstraint('log_id')
    )
    op.create_index(op.f('ix_service_account_api_key_log_api_key_id'), 'service_account_api_key_log', ['api_key_id'], unique=False)
    op.create_table('album_item',
    sa.Column('album_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('media_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('sort_index', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=True),
    sa.ForeignKeyConstraint(['album_id'], ['album.id'], ),
    sa.ForeignKeyConstraint(['media_id'], ['media.id'], ),
    sa.PrimaryKeyConstraint('album_id', 'media_id')
    )

def downgrade() -> None:
    op.drop_table('album_item')
    op.drop_index(op.f('ix_service_account_api_key_log_api_key_id'), table_name='service_account_api_key_log')
    op.drop_table('service_account_api_key_log')
    op.drop_index('idx_picker_selection_status_lock', table_name='picker_selection')
    op.drop_index('idx_picker_selection_session_status', table_name='picker_selection')
    op.drop_table('picker_selection')
    op.drop_table('media_tag')
    op.drop_table('media_sidecar')
    op.drop_table('media_playback')
    op.drop_index(op.f('ix_local_import_audit_log_timestamp'), table_name='local_import_audit_log')
    op.drop_index(op.f('ix_local_import_audit_log_task_id'), table_name='local_import_audit_log')
    op.drop_index(op.f('ix_local_import_audit_log_session_id'), table_name='local_import_audit_log')
    op.drop_index(op.f('ix_local_import_audit_log_request_id'), table_name='local_import_audit_log')
    op.drop_index(op.f('ix_local_import_audit_log_level'), table_name='local_import_audit_log')
    op.drop_index(op.f('ix_local_import_audit_log_item_id'), table_name='local_import_audit_log')
    op.drop_index(op.f('ix_local_import_audit_log_category'), table_name='local_import_audit_log')
    op.drop_index('idx_session_timestamp', table_name='local_import_audit_log')
    op.drop_index('idx_level_category', table_name='local_import_audit_log')
    op.drop_index('idx_item_timestamp', table_name='local_import_audit_log')
    op.drop_table('local_import_audit_log')
    op.drop_table('job_sync')
    op.drop_table('exif')
    op.drop_table('album')
    op.drop_table('wiki_revision')
    op.drop_table('wiki_page_category')
    op.drop_index(op.f('ix_service_account_api_key_service_account_id'), table_name='service_account_api_key')
    op.drop_table('service_account_api_key')
    op.drop_table('picker_session')
    op.drop_table('media')
    op.drop_index(op.f('ix_certificate_private_keys_expires_at'), table_name='certificate_private_keys')
    op.drop_index(op.f('ix_certificate_private_keys_created_at'), table_name='certificate_private_keys')
    op.drop_table('certificate_private_keys')
    op.drop_index(op.f('ix_wiki_page_slug'), table_name='wiki_page')
    op.drop_table('wiki_page')
    op.drop_table('user_roles')
    op.drop_index(op.f('ix_totp_credential_user_id'), table_name='totp_credential')
    op.drop_table('totp_credential')
    op.drop_table('tag')
    op.drop_table('service_account')
    op.drop_table('role_permissions')
    op.drop_index(op.f('ix_passkey_credential_user_id'), table_name='passkey_credential')
    op.drop_table('passkey_credential')
    op.drop_table('media_item')
    op.drop_index(op.f('ix_issued_certificates_usage_type'), table_name='issued_certificates')
    op.drop_index(op.f('ix_issued_certificates_issued_at'), table_name='issued_certificates')
    op.drop_index(op.f('ix_issued_certificates_expires_at'), table_name='issued_certificates')
    op.drop_table('issued_certificates')
    op.drop_table('group_user_membership')
    op.drop_table('google_account')
    op.drop_index('ix_worker_log_file_task_id_progress_step', table_name='worker_log')
    op.drop_index('ix_worker_log_file_task_id', table_name='worker_log')
    op.drop_index('ix_worker_log_event', table_name='worker_log')
    op.drop_table('worker_log')
    op.drop_index(op.f('ix_wiki_category_slug'), table_name='wiki_category')
    op.drop_table('wiki_category')
    op.drop_table('video_metadata')
    op.drop_table('user_group')
    op.drop_index(op.f('ix_user_email'), table_name='user')
    op.drop_table('user')
    op.drop_table('system_settings')
    op.drop_table('role')
    op.drop_table('picker_import_task')
    op.drop_table('photo_metadata')
    op.drop_table('permission')
    op.drop_index(op.f('ix_password_reset_token_email'), table_name='password_reset_token')
    op.drop_table('password_reset_token')
    op.drop_table('log')
    op.drop_index(op.f('ix_certificate_groups_usage_type'), table_name='certificate_groups')
    op.drop_table('certificate_groups')
    op.drop_index(op.f('ix_certificate_events_target_kid'), table_name='certificate_events')
    op.drop_index(op.f('ix_certificate_events_target_group_code'), table_name='certificate_events')
    op.drop_index(op.f('ix_certificate_events_occurred_at'), table_name='certificate_events')
    op.drop_table('certificate_events')
    op.drop_index('ix_celery_task_task_name_status', table_name='celery_task')
    op.drop_index('ix_celery_task_object', table_name='celery_task')
    op.drop_table('celery_task')
