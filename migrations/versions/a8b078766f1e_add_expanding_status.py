"""Add expanding status to picker_session.status enum."""

from alembic import op
import sqlalchemy as sa  # noqa: F401  (needed for Alembic context)


# revision identifiers, used by Alembic.
revision = "a8b078766f1e"
down_revision = "31b1901dba43"
branch_labels = None
depends_on = None


_OLD_STATUSES = (
    "pending",
    "ready",
    "processing",
    "enqueued",
    "importing",
    "imported",
    "canceled",
    "expired",
    "error",
    "failed",
)

_NEW_STATUSES = (
    "pending",
    "ready",
    "expanding",
    "processing",
    "enqueued",
    "importing",
    "imported",
    "canceled",
    "expired",
    "error",
    "failed",
)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect in {"mysql", "mariadb"}:
        op.execute(
            "ALTER TABLE picker_session MODIFY COLUMN status "
            "ENUM('" + "','".join(_NEW_STATUSES) + "') "
            "NOT NULL DEFAULT 'pending'"
        )
    elif dialect == "postgresql":
        op.execute("ALTER TYPE picker_session_status ADD VALUE IF NOT EXISTS 'expanding'")
    else:
        # SQLiteなどはENUMを文字列として扱うため追加処理不要
        pass


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect in {"mysql", "mariadb"}:
        op.execute(
            "UPDATE picker_session SET status='processing' WHERE status='expanding'"
        )
        op.execute(
            "ALTER TABLE picker_session MODIFY COLUMN status "
            "ENUM('" + "','".join(_OLD_STATUSES) + "') "
            "NOT NULL DEFAULT 'pending'"
        )
    elif dialect == "postgresql":
        op.execute(
            "UPDATE picker_session SET status='processing' WHERE status='expanding'"
        )
        op.execute("ALTER TYPE picker_session_status RENAME TO picker_session_status_old")
        op.execute(
            "CREATE TYPE picker_session_status AS ENUM('"
            + "','".join(_OLD_STATUSES)
            + "')"
        )
        op.execute(
            "ALTER TABLE picker_session ALTER COLUMN status TYPE picker_session_status "
            "USING status::text::picker_session_status"
        )
        op.execute("DROP TYPE picker_session_status_old")
    else:
        pass
