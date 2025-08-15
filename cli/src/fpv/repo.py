from __future__ import annotations
from typing import Dict, Any, List
import os, json
from sqlalchemy import create_engine, select, insert, update, text
from sqlalchemy.engine import Engine
from core.models import google_account, job_sync, photo_models, media_playback, exif as exif_tbl
from .config import PhotoNestConfig

def get_engine(env: Dict[str, str] | None = None) -> Engine:
    env = env or os.environ
    url = env.get("FPV_DB_URL") or env.get("DATABASE_URI")
    if not url:
        raise RuntimeError("FPV_DB_URL or DATABASE_URI not set")
    return create_engine(url, future=True)


def get_active_accounts(engine: Engine, account_id: int | None = None):
    stmt = select(
        google_account.c.id,
        google_account.c.account_email,
        google_account.c.oauth_token_json,
    ).where(google_account.c.status == "active")
    if account_id is not None:
        stmt = stmt.where(google_account.c.id == account_id)
    with engine.begin() as conn:
        rows = conn.execute(stmt).mappings().all()
    return rows


def create_job(engine: Engine, *, account_id: int, target: str) -> int:
    stmt = insert(job_sync).values(
        account_id=account_id,
        target=target,
        status="running",
        created_at=text("UTC_TIMESTAMP()"),
    )
    with engine.begin() as conn:
        res = conn.execute(stmt)
        return int(res.inserted_primary_key[0])


def finalize_job(
    engine: Engine, *, job_id: int, account_id: int, status: str, stats: Dict[str, Any]
) -> None:
    with engine.begin() as conn:
        row = conn.execute(
            select(job_sync.c.stats_json).where(job_sync.c.id == job_id)
        ).first()
        cur = {}
        if row and row[0]:
            try:
                cur = json.loads(row[0])
            except Exception:
                cur = {}
        cur.update(stats)
        conn.execute(
            update(job_sync)
            .where(job_sync.c.id == job_id)
            .values(
                finished_at=text("UTC_TIMESTAMP()"),
                status=status,
                stats_json=json.dumps(cur, ensure_ascii=False),
            )
        )


def media_exists_by_hash(engine: Engine, hash_hex: str) -> bool:
    stmt = select(photo_models.Media.c.id).where(photo_models.Media.c.hash_sha256 == hash_hex).limit(1)
    with engine.begin() as conn:
        row = conn.execute(stmt).first()
    return row is not None


def upsert_media_playback_queue(engine: Engine, media_id: int, rel_path: str) -> None:
    stmt = insert(media_playback).values(
        media_id=media_id,
        preset="original",
        rel_path=rel_path,
        status="queued",
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def insert_media(
    engine: Engine,
    *,
    google_media_id: str | None,
    account_id: int | None,
    rel_path: str,
    sha256: str,
    bytes_: int,
    mime: str,
    width: int | None,
    height: int | None,
    duration_ms: int | None,
    shot_at_utc,
    is_video: bool,
) -> int:
    stmt = insert(photo_models.Media).values(
        google_media_id=google_media_id,
        account_id=account_id,
        local_rel_path=rel_path,
        hash_sha256=sha256,
        bytes=bytes_,
        mime_type=mime,
        width=width,
        height=height,
        duration_ms=duration_ms,
        shot_at=shot_at_utc,
        imported_at=text("UTC_TIMESTAMP()"),
        is_video=1 if is_video else 0,
        is_deleted=0,
        has_playback=0,
    )
    with engine.begin() as conn:
        res = conn.execute(stmt)
        return int(res.inserted_primary_key[0])


def upsert_exif(engine: Engine, media_id: int, raw_json: dict) -> None:
    photo = (raw_json or {}).get("photo", {})
    make = photo.get("cameraMake")
    model = photo.get("cameraModel")
    lens = photo.get("lens") or None
    iso = photo.get("isoEquivalent")
    shutter = photo.get("exposureTime")
    fnum = photo.get("apertureFNumber")
    focal = photo.get("focalLength")
    gps_lat = gps_lng = None
    stmt = insert(exif_tbl).values(
        media_id=media_id,
        camera_make=make,
        camera_model=model,
        lens=lens,
        iso=iso,
        shutter=shutter,
        f_number=fnum,
        focal_len=focal,
        gps_lat=gps_lat,
        gps_lng=gps_lng,
        raw_json=json.dumps(raw_json, ensure_ascii=False),
    ).on_conflict_do_update(
        index_elements=[exif_tbl.c.media_id],
        set_={
            "camera_make": stmt.excluded.camera_make,
            "camera_model": stmt.excluded.camera_model,
            "lens": stmt.excluded.lens,
            "iso": stmt.excluded.iso,
            "shutter": stmt.excluded.shutter,
            "f_number": stmt.excluded.f_number,
            "focal_len": stmt.excluded.focal_len,
            "gps_lat": stmt.excluded.gps_lat,
            "gps_lng": stmt.excluded.gps_lng,
            "raw_json": stmt.excluded.raw_json,
        }
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def update_job_stats(engine: Engine, job_id: int, **delta_counts) -> None:
    with engine.begin() as conn:
        row = conn.execute(
            select(job_sync.c.stats_json).where(job_sync.c.id == job_id)
        ).first()
        cur = {}
        if row and row[0]:
            try:
                cur = json.loads(row[0])
            except Exception:
                cur = {}
        for k, v in delta_counts.items():
            cur[k] = int(cur.get(k, 0)) + int(v)
        conn.execute(
            update(job_sync)
            .where(job_sync.c.id == job_id)
            .values(stats_json=json.dumps(cur, ensure_ascii=False))
        )


def save_pagination_cursor(
    engine: Engine, job_id: int, next_page_token: str | None
) -> None:
    with engine.begin() as conn:
        row = conn.execute(
            select(job_sync.c.stats_json).where(job_sync.c.id == job_id)
        ).first()
        cur = {}
        if row and row[0]:
            try:
                cur = json.loads(row[0])
            except Exception:
                cur = {}
        if next_page_token:
            cur["cursor"] = {"nextPageToken": next_page_token}
        else:
            cur.pop("cursor", None)
        conn.execute(
            update(job_sync)
            .where(job_sync.c.id == job_id)
            .values(stats_json=json.dumps(cur, ensure_ascii=False))
        )
