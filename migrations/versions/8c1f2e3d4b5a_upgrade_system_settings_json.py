from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa

from core.system_settings_defaults import (
    DEFAULT_APPLICATION_SETTINGS,
    DEFAULT_CORS_SETTINGS,
)

# revision identifiers, used by Alembic.
revision = "8c1f2e3d4b5a"
down_revision = "1f0a4c2b8d7e"
branch_labels = None
depends_on = None


SYSTEM_SETTINGS_COLUMNS = [
    sa.Column(
        "id",
        sa.BigInteger().with_variant(sa.Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    sa.Column("setting_key", sa.String(length=100), nullable=False, unique=True),
    sa.Column("setting_json", sa.JSON(), nullable=False),
    sa.Column("description", sa.Text(), nullable=True),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        server_onupdate=sa.func.now(),
    ),
]


def upgrade() -> None:
    bind = op.get_bind()

    op.rename_table("system_settings", "system_settings_legacy")
    op.create_table("system_settings", *SYSTEM_SETTINGS_COLUMNS, sqlite_autoincrement=True)

    legacy_rows = list(
        bind.execute(sa.text("SELECT key, value FROM system_settings_legacy"))
    )

    settings_table = sa.table(
        "system_settings",
        sa.column("setting_key", sa.String(length=100)),
        sa.column("setting_json", sa.JSON()),
        sa.column("description", sa.Text()),
    )

    inserts = []
    for row in legacy_rows:
        key = row.key
        raw_value = row.value
        payload = None
        if raw_value:
            try:
                payload = json.loads(raw_value)
            except (TypeError, json.JSONDecodeError):
                payload = {"value": raw_value}
        if payload is None:
            payload = {}
        inserts.append(
            {
                "setting_key": key,
                "setting_json": payload,
                "description": "Migrated legacy configuration.",
            }
        )

    default_records = [
        {
            "setting_key": "app.config",
            "setting_json": DEFAULT_APPLICATION_SETTINGS,
            "description": "Application configuration values.",
        },
        {
            "setting_key": "app.cors",
            "setting_json": DEFAULT_CORS_SETTINGS,
            "description": "CORS configuration.",
        },
    ]

    op.bulk_insert(settings_table, default_records + inserts)

    op.drop_table("system_settings_legacy")


def downgrade() -> None:
    bind = op.get_bind()

    op.rename_table("system_settings", "system_settings_new")

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=120), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            server_onupdate=sa.func.now(),
        ),
        sqlite_autoincrement=True,
    )

    legacy_rows = list(
        bind.execute(sa.text("SELECT setting_key, setting_json FROM system_settings_new"))
    )

    legacy_table = sa.table(
        "system_settings",
        sa.column("key", sa.String(length=120)),
        sa.column("value", sa.Text()),
    )

    inserts = []
    for row in legacy_rows:
        serialized = json.dumps(row.setting_json, ensure_ascii=False)
        inserts.append({"key": row.setting_key, "value": serialized})

    if inserts:
        op.bulk_insert(legacy_table, inserts)

    op.drop_table("system_settings_new")
