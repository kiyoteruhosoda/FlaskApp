"""Add media_thumbnail_retry tracking table."""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9b8c9d89f1d'
down_revision = '31b1901dba43'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'media_thumbnail_retry',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
        sa.Column('media_id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('retry_after', sa.DateTime(timezone=True), nullable=False),
        sa.Column('force', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('celery_task_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['media_id'], ['media.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('media_id'),
    )


def downgrade():
    op.drop_table('media_thumbnail_retry')

