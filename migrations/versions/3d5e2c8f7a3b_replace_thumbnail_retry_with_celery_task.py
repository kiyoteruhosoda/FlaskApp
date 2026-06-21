"""Replace media thumbnail retry table with generic celery task tracking."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import json


# revision identifiers, used by Alembic.
revision = '3d5e2c8f7a3b'
down_revision = 'b9b8c9d89f1d'
branch_labels = None
depends_on = None


def _safe_dumps(payload):
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except TypeError:
        return json.dumps(str(payload), ensure_ascii=False)


def upgrade() -> None:
    op.create_table(
        'celery_task',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('task_name', sa.String(length=255), nullable=False),
        sa.Column('object_type', sa.String(length=64), nullable=True),
        sa.Column('object_id', sa.String(length=255), nullable=True),
        sa.Column('celery_task_id', sa.String(length=255), nullable=True, unique=True),
        sa.Column(
            'status',
            sa.Enum(
                'scheduled',
                'queued',
                'running',
                'success',
                'failed',
                'canceled',
                name='celery_task_status',
            ),
            nullable=False,
            server_default='queued',
        ),
        sa.Column('scheduled_for', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('payload_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('result_json', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_celery_task_task_name_status', 'celery_task', ['task_name', 'status'])
    op.create_index('ix_celery_task_object', 'celery_task', ['object_type', 'object_id'])

    connection = op.get_bind()
    metadata = sa.MetaData(bind=connection)

    inspector = sa.inspect(connection)

    if inspector.has_table('media_thumbnail_retry'):
        retry_table = sa.Table('media_thumbnail_retry', metadata, autoload_with=connection)
        celery_table = sa.Table('celery_task', metadata, autoload_with=connection)
        rows = list(connection.execute(sa.select(retry_table.c.media_id, retry_table.c.retry_after, retry_table.c.force, retry_table.c.celery_task_id)))
        if rows:
            connection.execute(
                celery_table.insert(),
                [
                    {
                        'task_name': 'thumbnail.retry',
                        'object_type': 'media',
                        'object_id': str(row.media_id) if row.media_id is not None else None,
                        'celery_task_id': row.celery_task_id,
                        'status': 'scheduled',
                        'scheduled_for': row.retry_after,
                        'payload_json': _safe_dumps({'force': bool(row.force)}),
                    }
                    for row in rows
                ],
            )

    op.add_column('job_sync', sa.Column('celery_task_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        'job_sync_celery_task_id_fkey',
        'job_sync',
        'celery_task',
        ['celery_task_id'],
        ['id'],
    )

    if inspector.has_table('media_thumbnail_retry'):
        op.drop_table('media_thumbnail_retry')


def downgrade() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData(bind=connection)
    inspector = sa.inspect(connection)

    op.drop_constraint('job_sync_celery_task_id_fkey', 'job_sync', type_='foreignkey')
    op.drop_column('job_sync', 'celery_task_id')

    op.create_table(
        'media_thumbnail_retry',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('media_id', sa.BigInteger(), nullable=False, unique=True),
        sa.Column('retry_after', sa.DateTime(), nullable=False),
        sa.Column('force', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('celery_task_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    if inspector.has_table('celery_task'):
        celery_table = sa.Table('celery_task', metadata, autoload_with=connection)
        retry_rows = list(
            connection.execute(
                sa.select(
                    celery_table.c.object_id,
                    celery_table.c.scheduled_for,
                    celery_table.c.payload_json,
                    celery_table.c.celery_task_id,
                ).where(celery_table.c.task_name == 'thumbnail.retry')
            )
        )
        if retry_rows:
            retry_table = sa.Table('media_thumbnail_retry', metadata, autoload_with=connection)
            payloads = []
            for row in retry_rows:
                if row.object_id is None:
                    continue
                payload = {}
                if row.payload_json:
                    try:
                        payload = json.loads(row.payload_json)
                    except json.JSONDecodeError:
                        payload = {}
                payloads.append(
                    {
                        'media_id': int(row.object_id),
                        'retry_after': row.scheduled_for or sa.func.now(),
                        'force': bool(payload.get('force', False)),
                        'celery_task_id': row.celery_task_id,
                    }
                )
            connection.execute(retry_table.insert(), payloads)

    op.drop_index('ix_celery_task_object', table_name='celery_task')
    op.drop_index('ix_celery_task_task_name_status', table_name='celery_task')
    op.drop_table('celery_task')
