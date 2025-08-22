from __future__ import annotations

"""Photo picker import task.

This module implements a simplified version of the specification provided in
``T-WKR-1``.  It avoids a hard dependency on Celery so that the function can be
invoked directly in tests.  The function follows the public contract of the
worker:

>>> picker_import(picker_session_id=1, account_id=1)
{"ok": True, "imported": 0, "dup": 0, "failed": 0}

The implementation is intentionally compact and omits many production features
(resume support, structured logging, exponential backoff, etc.) but captures the
core control‑flow so that unit tests can exercise the behaviour of the worker.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Dict, Iterable, List, Tuple

import requests
from sqlalchemy import update

from core.crypto import decrypt
from core.db import db
from core.models.google_account import GoogleAccount
from core.models.picker_session import PickerSession
from core.models.photo_models import (
    Exif,
    Media,
    MediaItem,
    MediaPlayback,
    PickerSelection,
)
from flask import current_app

# ---------------------------------------------------------------------------
# Queue hook
# ---------------------------------------------------------------------------

def enqueue_picker_import_item(selection_id: int) -> None:
    """Enqueue import task for a single picked media item.

    The real application would push a job onto a background worker system
    such as Celery.  For the purposes of the tests this function merely acts
    as a hook that can be monkeypatched to observe which items would be
    queued.
    """

    # The default implementation is a no-op; tests are expected to
    # monkeypatch this function.
    return None


def enqueue_thumbs_generate(media_id: int) -> None:
    """Enqueue thumbnail generation for *media_id*.

    This is a hook allowing tests to observe which media would have their
    thumbnails generated.  The default implementation is a no-op.
    """

    return None


def enqueue_media_playback(media_id: int) -> None:
    """Enqueue playback generation for a video *media_id*.

    The real application would push a job onto a background worker.  Tests can
    monkeypatch this function to inspect the queued items.
    """

    return None


def picker_import_queue_scan() -> Dict[str, int]:
    """Publish ``enqueued`` :class:`PickerSelection` rows to the worker queue."""

    queued = 0
    now = datetime.now(timezone.utc)

    selections: List[PickerSelection] = (
        PickerSelection.query.filter_by(status="enqueued").order_by(PickerSelection.id).all()
    )

    for sel in selections:
        sel.enqueued_at = sel.enqueued_at or now
        enqueue_picker_import_item(sel.id)
        queued += 1

    if queued:
        db.session.commit()

    return {"queued": queued}

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

@dataclass
class Downloaded:
    path: Path
    bytes: int
    sha256: str


def _guess_ext(filename: str | None, mime: str | None) -> str:
    """Return file extension including dot."""
    if filename and "." in filename:
        return os.path.splitext(filename)[1]
    if mime:
        if mime == "image/jpeg":
            return ".jpg"
        if mime == "image/png":
            return ".png"
        if mime == "image/heic" or mime == "image/heif":
            return ".heic"
        if mime == "video/mp4":
            return ".mp4"
        if mime == "video/quicktime":
            return ".mov"
    return ""


def _download(url: str, dest_dir: Path, headers: Dict[str, str] | None = None) -> Downloaded:
    """Download URL to *dest_dir* returning :class:`Downloaded`.

    The optional *headers* parameter allows authenticated downloads.
    """
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    tmp_name = hashlib.sha1(url.encode("utf-8")).hexdigest()
    tmp_path = dest_dir / tmp_name
    with open(tmp_path, "wb") as fh:
        fh.write(resp.content)
    sha = hashlib.sha256(resp.content).hexdigest()
    return Downloaded(tmp_path, len(resp.content), sha)


def _ensure_dirs() -> Tuple[Path, Path]:
    """Return (tmp_dir, originals_dir) creating them if necessary."""
    tmp_dir = Path(os.environ.get("FPV_TMP_DIR", "/tmp/fpv_tmp"))
    orig_dir = Path(os.environ.get("FPV_NAS_ORIG_DIR", "/tmp/fpv_orig"))
    tmp_dir.mkdir(parents=True, exist_ok=True)
    orig_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir, orig_dir


def _chunk(iterable: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


def _start_lock_heartbeat(selection_id: int, locked_by: str, interval: float) -> tuple[threading.Event, threading.Thread]:
    """Start background thread sending lock heartbeats."""

    stop = threading.Event()
    app = current_app._get_current_object()

    def _beat() -> None:
        with app.app_context():
            while not stop.is_set():
                ts = datetime.now(timezone.utc)
                with db.engine.begin() as conn:
                    conn.execute(
                        update(PickerSelection)
                        .where(
                            PickerSelection.id == selection_id,
                            PickerSelection.locked_by == locked_by,
                        )
                        .values(lock_heartbeat_at=ts)
                    )
                stop.wait(interval)

    thread = threading.Thread(target=_beat, daemon=True)
    thread.start()
    return stop, thread


# ---------------------------------------------------------------------------
# Internal helpers for main import task
# ---------------------------------------------------------------------------


def _lookup_session_and_account(picker_session_id: int, account_id: int) -> tuple[PickerSession | None, GoogleAccount | None, str | None]:
    ps = PickerSession.query.get(picker_session_id)
    if not ps or ps.account_id != account_id:
        return None, None, "invalid_session"
    if ps.status in {"imported", "canceled", "expired"}:
        return ps, None, "already_done"
    gacc = GoogleAccount.query.get(account_id)
    if not gacc:
        return ps, None, "account_not_found"
    return ps, gacc, None


def _exchange_refresh_token(gacc: GoogleAccount, ps: PickerSession) -> tuple[str | None, str | None]:
    try:
        token_data = json.loads(decrypt(gacc.oauth_token_json))
        refresh_token = token_data.get("refresh_token")
    except Exception:
        ps.status = "error"
        db.session.commit()
        return None, "token_error"

    try:
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
                "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        data = resp.json()
    except Exception:
        ps.status = "error"
        db.session.commit()
        return None, "oauth_error"

    if resp.status_code == 401 or data.get("error") == "invalid_grant":
        ps.status = "failed"
        db.session.commit()
        return None, "oauth_failed"

    if resp.status_code >= 400 or "access_token" not in data:
        ps.status = "error"
        db.session.commit()
        return None, "oauth_error"

    return data["access_token"], None


def _fetch_selected_ids(ps: PickerSession, headers: Dict[str, str]) -> tuple[List[str], str | None]:
    selected_ids: List[str] = []
    if ps.session_id:
        try:
            r = requests.get(
                f"https://photospicker.googleapis.com/v1/sessions/{ps.session_id}",
                headers=headers,
            )
            r.raise_for_status()
            sess_data = r.json()
            if sess_data.get("selectedMediaItemIds"):
                selected_ids = list(sess_data["selectedMediaItemIds"])
            elif sess_data.get("selectedMediaItems"):
                selected_ids = [m["id"] for m in sess_data["selectedMediaItems"]]
        except Exception:
            ps.status = "error"
            db.session.commit()
            return [], "session_get_error"

    count = len(selected_ids)
    ps.selected_count = count
    ps.media_items_set = count > 0

    if count == 0:
        ps.status = "ready"
        db.session.commit()
        return [], "no_selection"

    return selected_ids, None


# ---------------------------------------------------------------------------
# Per item import
# ---------------------------------------------------------------------------


def picker_import_item(
    *,
    selection_id: int,
    session_id: int,
    locked_by: str = "worker",
    heartbeat_interval: float = 30.0,
) -> Dict[str, object]:
    """Import a single :class:`PickerSelection`.

    The function now performs an atomic claim of the selection row and updates
    lock heartbeat timestamps while processing the item.
    """

    now = datetime.now(timezone.utc)

    stmt = (
        update(PickerSelection)
        .where(
            PickerSelection.id == selection_id,
            PickerSelection.session_id == session_id,
            PickerSelection.status == "enqueued",
        )
        .values(
            status="running",
            locked_by=locked_by,
            lock_heartbeat_at=now,
            attempts=PickerSelection.attempts + 1,
            started_at=now,
            last_transition_at=now,
        )
    )
    res = db.session.execute(stmt)
    if res.rowcount == 0:
        db.session.rollback()
        return {"ok": False, "error": "not_enqueued"}
    db.session.commit()

    sel = PickerSelection.query.get(selection_id)
    if not sel:
        return {"ok": False, "error": "not_found"}

    stop_evt, hb_thread = _start_lock_heartbeat(sel.id, locked_by, heartbeat_interval)

    tmp_dir, orig_dir = _ensure_dirs()

    try:
        # Retrieve account and access token
        ps = PickerSession.query.get(session_id)
        gacc = GoogleAccount.query.get(ps.account_id) if ps else None
        if not ps or not gacc:
            raise RuntimeError("account_not_found")
        access_token, note = _exchange_refresh_token(gacc, ps)
        if not access_token:
            raise RuntimeError(note or "oauth_failed")

        headers = {"Authorization": f"Bearer {access_token}"}

        # Fetch media item details to obtain base_url
        mi: MediaItem = sel.media_item  # type: ignore[assignment]
        try:
            r = requests.get(
                f"https://photospicker.googleapis.com/v1/mediaItems/{mi.id}",
                headers=headers,
            )
            r.raise_for_status()
            item = r.json()
        except Exception:
            raise RuntimeError("base_url_fetch_failed")

        base_url = item.get("baseUrl")
        if not base_url:
            raise RuntimeError("missing_base_url")

        meta = item.get("mediaMetadata", {})
        is_video = bool(meta.get("video")) or (mi.mime_type or "").startswith("video/")
        dl_url = base_url + ("=dv" if is_video else "=d")
        dl = _download(dl_url, tmp_dir, headers=headers)

        # Deduplication by hash
        if Media.query.filter_by(hash_sha256=dl.sha256).first():
            sel.status = "dup"
            dl.path.unlink(missing_ok=True)
        else:
            shot_at = sel.create_time or now
            ext = _guess_ext(mi.filename, mi.mime_type)
            out_rel = f"{shot_at:%Y/%m/%d}/{shot_at:%Y%m%d_%H%M%S}_picker_{dl.sha256[:8]}{ext}"
            final_path = orig_dir / out_rel
            final_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(dl.path, final_path)

            media = Media(
                google_media_id=mi.id,
                account_id=ps.account_id,
                local_rel_path=str(out_rel),
                hash_sha256=dl.sha256,
                bytes=dl.bytes,
                mime_type=mi.mime_type,
                width=int(meta.get("width", mi.width or 0) or 0),
                height=int(meta.get("height", mi.height or 0) or 0),
                duration_ms=int(meta.get("video", {}).get("durationMillis", 0) or 0)
                if is_video
                else None,
                shot_at=shot_at,
                imported_at=now,
                is_video=is_video,
            )
            db.session.add(media)
            db.session.flush()

            exif = Exif(media_id=media.id, raw_json=json.dumps(item))
            db.session.add(exif)

            if is_video:
                enqueue_media_playback(media.id)
            else:
                enqueue_thumbs_generate(media.id)

            sel.status = "imported"

    except Exception:
        sel.status = "failed"

    finally:
        stop_evt.set()
        hb_thread.join()
        end = datetime.now(timezone.utc)
        sel.finished_at = end
        sel.last_transition_at = end
        sel.locked_by = None
        sel.lock_heartbeat_at = None
        db.session.commit()

    return {"ok": sel.status in {"imported", "dup"}, "status": sel.status}


# ---------------------------------------------------------------------------
# Main task implementation
# ---------------------------------------------------------------------------


def picker_import(*, picker_session_id: int, account_id: int) -> Dict[str, object]:
    """Import media selected by the Google Photos Picker.

    The function returns a JSON‑serialisable dictionary describing the outcome
    of the import.  Errors are handled in a best‑effort manner and reflected in
    the ``note`` field of the response.
    """

    imported = 0
    dup = 0
    failed = 0
    note = None

    # 1. Lookup picker session and account
    ps, gacc, note = _lookup_session_and_account(picker_session_id, account_id)
    if note == "invalid_session":
        return {"ok": False, "imported": 0, "dup": 0, "failed": 0, "note": note}
    if note == "already_done":
        return {"ok": True, "imported": 0, "dup": 0, "failed": 0, "note": note}
    if note == "account_not_found":
        return {"ok": False, "imported": 0, "dup": 0, "failed": 0, "note": note}

    # 2. Exchange refresh token for access token
    access_token, note = _exchange_refresh_token(gacc, ps)  # type: ignore[arg-type]
    if note:
        return {"ok": False, "imported": 0, "dup": 0, "failed": 0, "note": note}

    headers = {"Authorization": f"Bearer {access_token}"}

    # 3. Fetch selected IDs from callback storage or picker session
    selected_ids, note = _fetch_selected_ids(ps, headers)  # type: ignore[arg-type]
    if note == "session_get_error":
        return {"ok": False, "imported": 0, "dup": 0, "failed": 0, "note": note}
    if note == "no_selection":
        return {"ok": True, "imported": 0, "dup": 0, "failed": 0}

    stats = ps.stats()
    stats["selected_count"] = len(selected_ids)
    processed_ids = stats.get("processed_ids", [])

    tmp_dir, orig_dir = _ensure_dirs()

    for chunk_ids in _chunk(selected_ids, 50):
        try:
            r = requests.post(
                "https://photospicker.googleapis.com/v1/mediaItems:batchGet",
                json={"mediaItemIds": chunk_ids},
                headers=headers,
            )
            r.raise_for_status()
            item_data = r.json()
        except Exception:
            failed += len(chunk_ids)
            continue

        # Extract list of media items depending on response structure
        results = []
        if isinstance(item_data, dict):
            if item_data.get("mediaItemResults"):
                for res in item_data["mediaItemResults"]:
                    if res.get("mediaItem"):
                        results.append(res["mediaItem"])
            elif item_data.get("mediaItems"):
                results.extend(item_data["mediaItems"])

        for item in results:
            media_id = item.get("id")
            if not media_id:
                failed += 1
                continue
            processed_ids.append(media_id)
            base_url = item.get("baseUrl")
            filename = item.get("filename")
            mime = item.get("mimeType")
            meta = item.get("mediaMetadata", {})
            is_video = bool(meta.get("video")) or (mime or "").startswith("video/")
            dl_url = base_url + ("=dv" if is_video else "=d")
            try:
                dl = _download(dl_url, tmp_dir)
            except Exception:
                failed += 1
                continue

            # Deduplication by hash
            if Media.query.filter_by(hash_sha256=dl.sha256).first():
                dup += 1
                dl.path.unlink(missing_ok=True)
                continue

            shot_at_str = meta.get("creationTime")
            try:
                shot_at = (
                    datetime.fromisoformat(shot_at_str.replace("Z", "+00:00"))
                    if shot_at_str
                    else datetime.now(timezone.utc)
                )
            except Exception:
                shot_at = datetime.now(timezone.utc)

            ext = _guess_ext(filename, mime)
            out_rel = (
                f"{shot_at:%Y/%m/%d}/{shot_at:%Y%m%d_%H%M%S}_picker_{dl.sha256[:8]}{ext}"
            )
            final_path = orig_dir / out_rel
            final_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(dl.path, final_path)

            media = Media(
                google_media_id=media_id,
                account_id=account_id,
                local_rel_path=str(out_rel),
                hash_sha256=dl.sha256,
                bytes=dl.bytes,
                mime_type=mime,
                width=int(meta.get("width", 0) or 0),
                height=int(meta.get("height", 0) or 0),
                duration_ms=int(meta.get("video", {}).get("durationMillis", 0) or 0),
                shot_at=shot_at,
                imported_at=datetime.now(timezone.utc),
                is_video=is_video,
            )
            db.session.add(media)
            db.session.flush()  # obtain media.id

            exif = Exif(media_id=media.id, raw_json=json.dumps(item))
            db.session.add(exif)

            if is_video:
                mp = (
                    MediaPlayback.query.filter_by(media_id=media.id, preset="std1080p").one_or_none()
                )
                if not mp:
                    mp = MediaPlayback(
                        media_id=media.id,
                        preset="std1080p",
                        status="queued",
                    )
                    db.session.add(mp)
                else:
                    mp.status = "queued"
            # image thumbnail tasks are not implemented; would be enqueued here

            imported += 1

        db.session.commit()

    stats["processed_ids"] = processed_ids
    ps.set_stats(stats)

    if imported > 0:
        ps.status = "imported"
        ps.completed_at = datetime.now(timezone.utc)
    elif failed > 0:
        ps.status = "error"
    else:  # only duplicates
        ps.status = "imported"
        ps.completed_at = datetime.now(timezone.utc)

    db.session.commit()

    ok = imported > 0 or failed == 0
    if imported > 0 and failed > 0:
        note = "partial"
    return {"ok": ok, "imported": imported, "dup": dup, "failed": failed, "note": note}


__all__ = [
    "picker_import",
    "enqueue_picker_import_item",
    "picker_import_item",
    "picker_import_queue_scan",
    "enqueue_thumbs_generate",
    "enqueue_media_playback",
]
