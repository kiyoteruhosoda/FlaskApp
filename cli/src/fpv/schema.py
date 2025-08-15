from __future__ import annotations
from sqlalchemy import (
    MetaData, Table, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, text
)

metadata = MetaData()

google_account = Table(
    "google_account", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("account_email", String(255), nullable=False),
    Column("oauth_token_json", Text, nullable=False),
    Column("status", String(32), nullable=False, default="active"),
)

job_sync = Table(
    "job_sync", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("account_id", Integer, nullable=False),
    Column("target", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("stats_json", Text),
    Column("created_at", DateTime, server_default=text("UTC_TIMESTAMP()")),
    Column("finished_at", DateTime),
)

media = Table(
    "media", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("google_media_id", String(255)),
    Column("account_id", Integer),
    Column("local_rel_path", String(255)),
    Column("hash_sha256", String(64)),
    Column("bytes", Integer),
    Column("mime_type", String(255)),
    Column("width", Integer),
    Column("height", Integer),
    Column("duration_ms", Integer),
    Column("shot_at", DateTime),
    Column("imported_at", DateTime),
    Column("is_video", Boolean),
    Column("is_deleted", Boolean),
    Column("has_playback", Boolean),
)

exif = Table(
    "exif", metadata,
    Column("media_id", Integer, primary_key=True),
    Column("camera_make", String(255)),
    Column("camera_model", String(255)),
    Column("lens", String(255)),
    Column("iso", Integer),
    Column("shutter", String(32)),
    Column("f_number", String(10)),
    Column("focal_len", String(10)),
    Column("gps_lat", String(32)),
    Column("gps_lng", String(32)),
    Column("raw_json", Text),
)

media_playback = Table(
    "media_playback", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("media_id", Integer, nullable=False),
    Column("preset", String(32)),
    Column("rel_path", String(255)),
    Column("status", String(32)),
)
