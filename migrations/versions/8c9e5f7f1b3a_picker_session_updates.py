from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8c9e5f7f1b3a'
down_revision = 'f1f22e95f3c7'
branch_labels = None
depends_on = None


def upgrade():
    status_enum = sa.Enum(
        'pending', 'ready', 'processing', 'enqueued', 'importing', 'imported',
        'canceled', 'expired', 'error', 'failed', name='picker_session_status'
    )
    status_enum.create(op.get_bind(), checkfirst=True)
    with op.batch_alter_table('picker_session') as batch:
        batch.add_column(sa.Column('last_progress_at', sa.DateTime(), nullable=True))
        batch.alter_column(
            'status',
            existing_type=sa.String(length=20),
            type_=status_enum,
            existing_nullable=False,
            server_default='pending',
        )


def downgrade():
    status_enum = sa.Enum(
        'pending', 'ready', 'processing', 'enqueued', 'importing', 'imported',
        'canceled', 'expired', 'error', 'failed', name='picker_session_status'
    )
    with op.batch_alter_table('picker_session') as batch:
        batch.alter_column(
            'status',
            existing_type=status_enum,
            type_=sa.String(length=20),
            existing_nullable=False,
        )
        batch.drop_column('last_progress_at')
    status_enum.drop(op.get_bind(), checkfirst=True)
