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
from datetime import datetime, timezone, timedelta
import contextlib
import errno
import hashlib
import json
import logging
import os
import shutil
import tempfile
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
from core.logging_config import setup_task_logging, log_task_error, log_task_info
from core.tasks.media_post_processing import (
    enqueue_media_playback as common_enqueue_media_playback,
    enqueue_thumbs_generate as common_enqueue_thumbs_generate,
    process_media_post_import,
)
from flask import current_app

# picker_import専用ロガーを取得（両方のログハンドラーが設定済み）
logger = logging.getLogger('picker_import')


def _fsync_dir(path: Path) -> None:
    """Best-effort fsync for directory entries."""

    try:
        dir_fd = os.open(str(path), os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


class AuthError(Exception):
    """Authorization failure that should not be retried."""


class NetworkError(Exception):
    """Transient network error that is safe to retry."""


class BaseUrlExpired(Exception):
    """Base URL could not be resolved and item should expire."""

# ---------------------------------------------------------------------------
# Queue hook
# ---------------------------------------------------------------------------

def enqueue_picker_import_item(selection_id: int, session_id: int) -> None:
    """Enqueue import task for a single picked media item.

    In production this would push a job onto a background worker system such
    as Celery.  For tests the function acts as a hook that can be
    monkeypatched to observe which items would be queued.
    """
    try:
        from cli.src.celery.tasks import picker_import_item_task
    except ImportError:
        return None

    try:
        picker_import_item_task.delay(selection_id, session_id)
    except Exception as exc:  # pragma: no cover - network failure path
        try:
            from flask import current_app

            if current_app and current_app.config.get("TESTING"):
                current_app.logger.warning(
                    "Celery worker unavailable for picker import item; skipping in test mode.",
                    extra={
                        "event": "picker.import.enqueue.skip",
                        "selection_id": selection_id,
                        "session_id": session_id,
                        "error": str(exc),
                    },
                )
                return None
        except RuntimeError:
            # Outside of Flask context (e.g., unit tests), simply ignore
            return None
        raise


def enqueue_thumbs_generate(media_id: int) -> None:
    """Backward compatible wrapper around the shared thumbnail helper."""

    common_enqueue_thumbs_generate(media_id, logger_override=logger)


def enqueue_media_playback(media_id: int) -> None:
    """Backward compatible wrapper around the shared video helper."""

    common_enqueue_media_playback(media_id, logger_override=logger)


def picker_import_queue_scan() -> Dict[str, int]:
    """Publish ``enqueued`` :class:`PickerSelection` rows to the worker queue."""

    queued = 0
    now = datetime.now(timezone.utc)

    selections: List[PickerSelection] = (
        PickerSelection.query.filter_by(status="enqueued").order_by(PickerSelection.id).all()
    )

    for sel in selections:
        sel.enqueued_at = sel.enqueued_at or now
        enqueue_picker_import_item(sel.id, sel.session_id)
        queued += 1

    if queued:
        db.session.commit()

    return {"queued": queued}


def backoff(attempts: int) -> timedelta:
    """Return retry delay for *attempts* using exponential backoff."""

    return timedelta(seconds=60 * (2 ** attempts))


def picker_import_watchdog(
    *,
    lock_lease: int = 120,
    stale_running: int = 600,
    max_attempts: int = 3,
) -> Dict[str, int]:
    """Housekeeping task for :class:`PickerSelection` rows.

    The function performs the following maintenance steps:

    1. ``running`` rows with expired heartbeats are released.  If the
       ``attempts`` value is below ``max_attempts`` the row returns to
       ``enqueued``.  Otherwise it is marked ``failed`` and ``finished_at`` is
       set.
    2. ``failed`` rows are retried once their backoff delay has elapsed.
    3. ``enqueued`` rows that have been waiting for more than five minutes are
       republished to the worker queue and a warning is logged.
    """

    now = datetime.now(timezone.utc)
    metrics = {"requeued": 0, "failed": 0, "recovered": 0, "republished": 0}

    # --- 1. handle stale running rows -----------------------------------
    running = PickerSelection.query.filter_by(status="running").all()
    for sel in running:
        hb = sel.lock_heartbeat_at
        if hb and hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
        started = sel.started_at
        if started and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)

        stale = False
        if hb is None or hb < now - timedelta(seconds=lock_lease):
            stale = True
        if started and started < now - timedelta(seconds=stale_running):
            stale = True

        if not stale:
            continue

        if sel.attempts < max_attempts:
            sel.status = "enqueued"
            sel.locked_by = None
            sel.lock_heartbeat_at = None
            sel.started_at = None
            sel.enqueued_at = now
            sel.last_transition_at = now
            metrics["requeued"] += 1
            logger.info(
                json.dumps(
                    {
                        "ts": now.isoformat(),
                        "selection_id": sel.id,
                        "attempts": sel.attempts,
                    }
                ),
                extra={"event": "scavenger.requeue"},
            )
        else:
            sel.status = "failed"
            sel.locked_by = None
            sel.lock_heartbeat_at = None
            sel.finished_at = now
            sel.last_transition_at = now
            metrics["failed"] += 1
            logger.info(
                json.dumps(
                    {
                        "ts": now.isoformat(),
                        "selection_id": sel.id,
                        "attempts": sel.attempts,
                    }
                ),
                extra={"event": "scavenger.finalize_failed"},
            )

    if metrics["requeued"] or metrics["failed"]:
        db.session.commit()

    # --- 2. retry failed rows after backoff ------------------------------
    failed_rows = PickerSelection.query.filter_by(status="failed").all()
    for sel in failed_rows:
        lt = sel.last_transition_at
        if lt and lt.tzinfo is None:
            lt = lt.replace(tzinfo=timezone.utc)
        if lt and lt + backoff(sel.attempts) <= now:
            sel.status = "enqueued"
            sel.enqueued_at = now
            sel.finished_at = None
            sel.last_transition_at = now
            metrics["recovered"] += 1
            logger.info(
                json.dumps(
                    {
                        "ts": now.isoformat(),
                        "selection_id": sel.id,
                        "attempts": sel.attempts,
                    }
                ),
                extra={"event": "scavenger.requeue"},
            )

    if metrics["recovered"]:
        db.session.commit()

    # --- 3. republish stalled enqueued rows ------------------------------
    enqueued_rows = PickerSelection.query.filter_by(status="enqueued").all()
    stale_threshold = now - timedelta(minutes=5)
    for sel in enqueued_rows:
        enq_at = sel.enqueued_at or sel.last_transition_at
        if not enq_at:
            continue
        if enq_at.tzinfo is None:
            enq_at = enq_at.replace(tzinfo=timezone.utc)
        if enq_at < stale_threshold:
            enqueue_picker_import_item(sel.id, sel.session_id)
            sel.enqueued_at = now
            metrics["republished"] += 1
            logger.warning("republished stalled selection %s", sel.id)

    if metrics["republished"]:
        db.session.commit()

    # --- 4. auto-complete finished sessions -----------------------------
    from core.models.picker_session import PickerSession
    from core.models.job_sync import JobSync
    
    # Find sessions in "importing" status that might be complete
    importing_sessions = PickerSession.query.filter_by(status="importing").all()
    metrics["completed_sessions"] = 0
    
    for ps in importing_sessions:
        # Check if all selections for this session are in terminal states
        selections = PickerSelection.query.filter_by(session_id=ps.id).all()
        if not selections:
            # No selections means import should be marked as completed (empty import)
            ps.status = "imported"
            ps.last_progress_at = now
            ps.updated_at = now
            
            # Update related job
            job = JobSync.query.filter_by(target="picker_import", session_id=ps.id).order_by(JobSync.id.desc()).first()
            if job and job.status in ("queued", "running"):
                job.finished_at = now
                job.status = "success"
                
                # Update job stats
                stats = json.loads(job.stats_json or "{}")
                stats["countsByStatus"] = {}
                stats["completed_at"] = now.isoformat()
                job.stats_json = json.dumps(stats)
            
            metrics["completed_sessions"] += 1
            logger.info(
                json.dumps({
                    "ts": now.isoformat(),
                    "session_id": ps.id,
                    "status": "imported",
                    "reason": "no_selections",
                }),
                extra={"event": "picker.session.auto_complete"},
            )
            continue
            
        terminal_states = {"imported", "dup", "failed", "expired"}
        all_terminal = all(sel.status in terminal_states for sel in selections)
        
        if all_terminal:
            # Count results
            status_counts = {}
            for sel in selections:
                status_counts[sel.status] = status_counts.get(sel.status, 0) + 1
            
            # Update session status
            has_imported = status_counts.get("imported", 0) > 0 or status_counts.get("dup", 0) > 0
            has_failed = status_counts.get("failed", 0) > 0 or status_counts.get("expired", 0) > 0
            
            if has_imported and not has_failed:
                ps.status = "imported"
            elif has_imported and has_failed:
                ps.status = "imported"  # Partial success still counts as imported
            else:
                ps.status = "error"
            
            ps.last_progress_at = now
            ps.updated_at = now
            
            # Update related job
            job = JobSync.query.filter_by(target="picker_import", session_id=ps.id).order_by(JobSync.id.desc()).first()
            if job and job.status in ("queued", "running"):
                job.finished_at = now
                if ps.status == "imported":
                    job.status = "success"
                else:
                    job.status = "failed"
                
                # Update job stats
                stats = json.loads(job.stats_json or "{}")
                stats["countsByStatus"] = status_counts
                stats["completed_at"] = now.isoformat()
                job.stats_json = json.dumps(stats)
            
            metrics["completed_sessions"] += 1
            logger.info(
                json.dumps({
                    "ts": now.isoformat(),
                    "session_id": ps.id,
                    "status": ps.status,
                    "counts": status_counts,
                }),
                extra={"event": "watchdog.session.complete"},
            )
    
    if metrics["completed_sessions"]:
        db.session.commit()

    return metrics

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
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        
        # ダウンロード成功ログ
        logger.info(
            f"ファイルダウンロード成功: {url} ({len(resp.content)} bytes)",
            extra={
                "event": "picker.download.success",
                "url": url,
                "content_length": len(resp.content),
                "status_code": resp.status_code
            }
        )
        
        tmp_name = hashlib.sha1(url.encode("utf-8")).hexdigest()
        tmp_path = dest_dir / tmp_name
        with open(tmp_path, "wb") as fh:
            fh.write(resp.content)
        sha = hashlib.sha256(resp.content).hexdigest()
        return Downloaded(tmp_path, len(resp.content), sha)
    except requests.Timeout as e:
        logger.error(
            f"ダウンロードタイムアウト: {url}",
            extra={
                "event": "picker.download.timeout",
                "url": url,
                "error_message": str(e)
            }
        )
        raise
    except requests.HTTPError as e:
        logger.error(
            f"ダウンロードHTTPエラー: {url} - Status: {e.response.status_code if e.response else 'Unknown'}",
            extra={
                "event": "picker.download.http_error",
                "url": url,
                "status_code": e.response.status_code if e.response else None,
                "response_text": e.response.text if e.response else None
            }
        )
        raise
    except Exception as e:
        logger.error(
            f"ダウンロード予期しないエラー: {url} - {str(e)}",
            extra={
                "event": "picker.download.error",
                "url": url,
                "error_type": type(e).__name__,
                "error_message": str(e)
            },
            exc_info=True
        )
        raise


def _ensure_dirs() -> Tuple[Path, Path]:
    """Return (tmp_dir, originals_dir) creating them if necessary."""
    tmp_dir = Path(os.environ.get("FPV_TMP_DIR", "/tmp/fpv_tmp"))
    orig_dir = Path(os.environ.get("FPV_NAS_ORIGINALS_DIR", "/tmp/fpv_orig"))
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
                logger.info(
                    json.dumps(
                        {
                            "ts": ts.isoformat(),
                            "selection_id": selection_id,
                            "locked_by": locked_by,
                        }
                    ),
                    extra={"event": "picker.item.heartbeat"},
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
                timeout=30
            )
            r.raise_for_status()
            sess_data = r.json()
            if sess_data.get("selectedMediaItemIds"):
                selected_ids = list(sess_data["selectedMediaItemIds"])
            elif sess_data.get("selectedMediaItems"):
                selected_ids = [m["id"] for m in sess_data["selectedMediaItems"]]
                
            logger.info(
                f"Google Photos セッション取得成功: session_id={ps.session_id}, 選択アイテム数={len(selected_ids)}",
                extra={
                    "event": "picker.session.fetch.success",
                    "picker_session_id": ps.id,
                    "google_session_id": ps.session_id,
                    "selected_count": len(selected_ids)
                }
            )
        except requests.HTTPError as e:
            error_details = {
                "picker_session_id": ps.id,
                "google_session_id": ps.session_id,
                "status_code": e.response.status_code if e.response else None,
                "response_text": e.response.text if e.response else None,
                "error_type": "HTTPError"
            }
            logger.error(
                f"Google Photos セッション取得HTTPエラー: session_id={ps.session_id} - {e}",
                extra={
                    "event": "picker.session.fetch.http_error",
                    "error_details": json.dumps(error_details)
                }
            )
            ps.status = "error"
            db.session.commit()
            return [], "session_get_error"
        except requests.RequestException as e:
            error_details = {
                "picker_session_id": ps.id,
                "google_session_id": ps.session_id,
                "error_type": "RequestException",
                "error_message": str(e)
            }
            logger.error(
                f"Google Photos セッション取得リクエストエラー: session_id={ps.session_id} - {e}",
                extra={
                    "event": "picker.session.fetch.request_error",
                    "error_details": json.dumps(error_details)
                }
            )
            ps.status = "error"
            db.session.commit()
            return [], "session_get_error"
        except Exception as e:
            error_details = {
                "picker_session_id": ps.id,
                "google_session_id": ps.session_id,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
            logger.error(
                f"Google Photos セッション取得予期しないエラー: session_id={ps.session_id} - {e}",
                extra={
                    "event": "picker.session.fetch.unexpected_error",
                    "error_details": json.dumps(error_details)
                },
                exc_info=True
            )
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

    logger.info(
        json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "selection_id": sel.id,
                "session_id": session_id,
                "locked_by": locked_by,
            }
        ),
        extra={"event": "picker.item.claim"},
    )

    stop_evt, hb_thread = _start_lock_heartbeat(sel.id, locked_by, heartbeat_interval)

    tmp_dir, orig_dir = _ensure_dirs()

    try:
        # Retrieve account and access token
        ps = PickerSession.query.get(session_id)
        gacc = GoogleAccount.query.get(ps.account_id) if ps else None
        if not ps or not gacc:
            raise AuthError()
        access_token, note = _exchange_refresh_token(gacc, ps)
        if not access_token:
            if note == "oauth_failed":
                raise AuthError()
            raise NetworkError()

        headers = {"Authorization": f"Bearer {access_token}"}

        mi: MediaItem = sel.media_item  # type: ignore[assignment]
        base_url: str | None = None
        item: dict | None = None
        now = datetime.now(timezone.utc)
        valid_until = sel.base_url_valid_until
        if valid_until and valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=timezone.utc)
        if sel.base_url and valid_until and valid_until > now:
            base_url = sel.base_url
        else:
            try:
                r = requests.get(
                    f"https://photospicker.googleapis.com/v1/mediaItems/{mi.id}",
                    headers=headers,
                    timeout=30
                )
                r.raise_for_status()
                item = r.json()
                
                logger.info(
                    f"Google Photos メディアアイテム取得成功: media_id={mi.id}",
                    extra={
                        "event": "picker.media.fetch.success",
                        "google_media_id": mi.id,
                        "selection_id": sel.id,
                        "session_id": session_id
                    }
                )
            except requests.HTTPError as e:
                error_details = {
                    "google_media_id": mi.id,
                    "selection_id": sel.id,
                    "session_id": session_id,
                    "status_code": e.response.status_code if e.response else None,
                    "response_text": e.response.text if e.response else None,
                    "error_type": "HTTPError"
                }
                if e.response is not None and e.response.status_code in (401, 403):
                    logger.error(
                        f"Google Photos メディアアイテム取得認証エラー: media_id={mi.id} - {e}",
                        extra={
                            "event": "picker.media.fetch.auth_error",
                            "error_details": json.dumps(error_details)
                        }
                    )
                    raise AuthError()
                elif e.response is not None and e.response.status_code == 404:
                    logger.warning(
                        f"Google Photos メディアアイテムが見つからない: media_id={mi.id} - {e}",
                        extra={
                            "event": "picker.media.fetch.not_found",
                            "error_details": json.dumps(error_details)
                        }
                    )
                    raise BaseUrlExpired()
                else:
                    logger.error(
                        f"Google Photos メディアアイテム取得HTTPエラー: media_id={mi.id} - {e}",
                        extra={
                            "event": "picker.media.fetch.http_error",
                            "error_details": json.dumps(error_details)
                        }
                    )
                    raise NetworkError()
            except requests.RequestException as e:
                error_details = {
                    "google_media_id": mi.id,
                    "selection_id": sel.id,
                    "session_id": session_id,
                    "error_type": "RequestException",
                    "error_message": str(e)
                }
                logger.error(
                    f"Google Photos メディアアイテム取得リクエストエラー: media_id={mi.id} - {e}",
                    extra={
                        "event": "picker.media.fetch.request_error",
                        "error_details": json.dumps(error_details)
                    }
                )
                raise NetworkError()
            except Exception as e:
                error_details = {
                    "google_media_id": mi.id,
                    "selection_id": sel.id,
                    "session_id": session_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
                logger.error(
                    f"Google Photos メディアアイテム取得予期しないエラー: media_id={mi.id} - {e}",
                    extra={
                        "event": "picker.media.fetch.unexpected_error",
                        "error_details": json.dumps(error_details)
                    },
                    exc_info=True
                )
                raise NetworkError()

            base_url = item.get("baseUrl")
            if not base_url:
                raise BaseUrlExpired()
            sel.base_url = base_url
            sel.base_url_fetched_at = now
            sel.base_url_valid_until = now + timedelta(hours=1)

        meta = item.get("mediaMetadata", {}) if item else {}
        is_video = bool(meta.get("video")) or (mi.mime_type or "").startswith("video/")
        dl_url = base_url + ("=dv" if is_video else "=d")
        try:
            dl = _download(dl_url, tmp_dir, headers=headers)
        except requests.HTTPError as e:
            # HTTPエラーの詳細をログDBに記録
            error_details = {
                "ts": now.isoformat(),
                "selection_id": sel.id,
                "session_id": session_id,
                "url": dl_url,
                "status_code": e.response.status_code if e.response else None,
                "response_text": e.response.text if e.response else None,
                "error_type": "HTTPError",
                "google_media_id": mi.id,
                "filename": mi.filename,
                "mime_type": mi.mime_type
            }
            logger.error(
                f"ファイルダウンロード失敗 (HTTP Error): {e}",
                extra={
                    "event": "picker.download.failed.http",
                    "error_details": json.dumps(error_details)
                }
            )
            if e.response is not None and e.response.status_code in (401, 403):
                raise AuthError()
            raise NetworkError()
        except requests.RequestException as e:
            # リクエスト例外の詳細をログDBに記録
            error_details = {
                "ts": now.isoformat(),
                "selection_id": sel.id,
                "session_id": session_id,
                "url": dl_url,
                "error_type": "RequestException",
                "error_message": str(e),
                "google_media_id": mi.id,
                "filename": mi.filename,
                "mime_type": mi.mime_type
            }
            logger.error(
                f"ファイルダウンロード失敗 (Request Error): {e}",
                extra={
                    "event": "picker.download.failed.request",
                    "error_details": json.dumps(error_details)
                }
            )
            raise NetworkError()
        except Exception as e:
            # その他の予期しないエラーもログDBに記録
            error_details = {
                "ts": now.isoformat(),
                "selection_id": sel.id,
                "session_id": session_id,
                "url": dl_url,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "google_media_id": mi.id,
                "filename": mi.filename,
                "mime_type": mi.mime_type
            }
            logger.error(
                f"ファイルダウンロード失敗 (Unexpected Error): {e}",
                extra={
                    "event": "picker.download.failed.unexpected",
                    "error_details": json.dumps(error_details)
                },
                exc_info=True
            )
            raise

        # Deduplication by hash
        if Media.query.filter_by(hash_sha256=dl.sha256, is_deleted=False).first():
            sel.status = "dup"
            dl.path.unlink(missing_ok=True)
        else:
            shot_at = sel.create_time or now
            ext = _guess_ext(mi.filename, mi.mime_type)
            out_rel = f"{shot_at:%Y/%m/%d}/{shot_at:%Y%m%d_%H%M%S}_picker_{dl.sha256[:8]}{ext}"
            final_path = orig_dir / out_rel
            final_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                move_method = "replace"
                try:
                    os.replace(dl.path, final_path)
                except OSError as e:
                    if e.errno == errno.EXDEV:
                        move_method = "copy+replace"
                        fd, tmp_name = tempfile.mkstemp(
                            dir=str(final_path.parent), prefix=".tmp_picker_import_"
                        )
                        tmp_path = Path(tmp_name)
                        try:
                            with os.fdopen(fd, "wb", closefd=True) as wf, dl.path.open(
                                "rb"
                            ) as rf:
                                shutil.copyfileobj(rf, wf, length=16 * 1024 * 1024)
                                wf.flush()
                                os.fsync(wf.fileno())
                            with contextlib.suppress(OSError):
                                shutil.copystat(dl.path, tmp_path, follow_symlinks=True)
                            _fsync_dir(final_path.parent)
                            os.replace(tmp_path, final_path)
                            _fsync_dir(final_path.parent)
                        except Exception:
                            with contextlib.suppress(FileNotFoundError):
                                tmp_path.unlink()
                            raise
                        with contextlib.suppress(FileNotFoundError):
                            dl.path.unlink()
                        logger.warning(
                            f"クロスデバイス移動を検知しコピーで保存: {dl.path} -> {final_path}",
                            extra={
                                "event": "picker.file.move.cross_device",
                                "selection_id": sel.id,
                                "session_id": session_id,
                                "sha256": dl.sha256,
                            },
                        )
                    else:
                        raise

                # ファイル保存ログ
                logger.info(
                    json.dumps(
                        {
                            "ts": now.isoformat(),
                            "selection_id": sel.id,
                            "session_id": session_id,
                            "file_path": str(final_path),
                            "file_size": dl.bytes,
                            "mime_type": mi.mime_type,
                            "sha256": dl.sha256,
                            "original_filename": mi.filename,
                            "move_method": move_method,
                        }
                    ),
                    extra={"event": "picker.file.saved"},
                )
            except OSError as e:
                # ファイル移動エラーをログDBに記録
                error_details = {
                    "ts": now.isoformat(),
                    "selection_id": sel.id,
                    "session_id": session_id,
                    "source_path": str(dl.path),
                    "dest_path": str(final_path),
                    "error_type": "OSError",
                    "error_message": str(e),
                    "google_media_id": mi.id,
                    "filename": mi.filename,
                    "sha256": dl.sha256
                }
                logger.error(
                    f"ファイル移動失敗: {dl.path} -> {final_path} - {e}",
                    extra={
                        "event": "picker.file.move.failed",
                        "error_details": json.dumps(error_details)
                    }
                )
                # 一時ファイルのクリーンアップ
                dl.path.unlink(missing_ok=True)
                raise
            except Exception as e:
                # その他のファイル操作エラーをログDBに記録
                error_details = {
                    "ts": now.isoformat(),
                    "selection_id": sel.id,
                    "session_id": session_id,
                    "source_path": str(dl.path),
                    "dest_path": str(final_path),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "google_media_id": mi.id,
                    "filename": mi.filename,
                    "sha256": dl.sha256
                }
                logger.error(
                    f"ファイル操作予期しないエラー: {dl.path} -> {final_path} - {e}",
                    extra={
                        "event": "picker.file.operation.failed",
                        "error_details": json.dumps(error_details)
                    },
                    exc_info=True
                )
                # 一時ファイルのクリーンアップ
                dl.path.unlink(missing_ok=True)
                raise

            try:
                media = Media(
                    source_type="google_photos",
                    google_media_id=mi.id,
                    account_id=ps.account_id,
                    local_rel_path=str(out_rel),
                    filename=mi.filename or Path(out_rel).name,
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

                exif = Exif(media_id=media.id, raw_json=json.dumps(item or {}))
                db.session.add(exif)

                process_media_post_import(
                    media,
                    logger_override=logger,
                    request_context={
                        "session_id": session_id,
                        "selection_id": sel.id,
                        "source": "picker_import",
                    },
                )

                sel.status = "imported"
                
                # DB登録成功ログ
                logger.info(
                    f"メディアDB登録成功: media_id={media.id}, google_media_id={mi.id}",
                    extra={
                        "event": "picker.media.db.saved",
                        "media_id": media.id,
                        "google_media_id": mi.id,
                        "selection_id": sel.id,
                        "session_id": session_id
                    }
                )
            except Exception as e:
                # DB登録エラーをログDBに記録
                error_details = {
                    "ts": now.isoformat(),
                    "selection_id": sel.id,
                    "session_id": session_id,
                    "google_media_id": mi.id,
                    "filename": mi.filename,
                    "sha256": dl.sha256,
                    "file_path": str(final_path),
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
                logger.error(
                    f"メディアDB登録失敗: {mi.id} - {e}",
                    extra={
                        "event": "picker.media.db.failed",
                        "error_details": json.dumps(error_details)
                    },
                    exc_info=True
                )
                # ファイルのクリーンアップ（DB登録に失敗した場合）
                try:
                    final_path.unlink(missing_ok=True)
                    logger.info(f"DB登録失敗によりファイルクリーンアップ: {final_path}")
                except Exception as cleanup_error:
                    logger.warning(f"ファイルクリーンアップ失敗: {final_path} - {cleanup_error}")
                raise

    except AuthError as e:
        sel.status = "failed"
        sel.error_msg = str(e)
        logger.error(
            f"認証エラー: selection_id={sel.id} - {e}",
            extra={
                "event": "picker.import.auth_error",
                "selection_id": sel.id,
                "session_id": session_id,
                "error_message": str(e)
            }
        )
    except BaseUrlExpired as e:
        sel.status = "expired"
        sel.error_msg = str(e)
        logger.warning(
            f"ベースURL有効期限切れ: selection_id={sel.id} - {e}",
            extra={
                "event": "picker.import.url_expired",
                "selection_id": sel.id,
                "session_id": session_id,
                "error_message": str(e)
            }
        )
    except NetworkError as e:
        sel.status = "enqueued"
        sel.error_msg = str(e)
        logger.warning(
            f"ネットワークエラー（再試行予定）: selection_id={sel.id} - {e}",
            extra={
                "event": "picker.import.network_error",
                "selection_id": sel.id,
                "session_id": session_id,
                "error_message": str(e)
            }
        )
    except Exception as e:
        sel.status = "failed"
        sel.error_msg = str(e)
        logger.error(
            f"予期しないエラー: selection_id={sel.id} - {e}",
            extra={
                "event": "picker.import.unexpected_error",
                "selection_id": sel.id,
                "session_id": session_id,
                "error_type": type(e).__name__,
                "error_message": str(e)
            },
            exc_info=True
        )

    finally:
        stop_evt.set()
        hb_thread.join()
        end = datetime.now(timezone.utc)
        terminal = {"imported", "dup", "failed", "expired"}
        if sel.status in terminal:
            sel.finished_at = end
            ps = PickerSession.query.get(session_id)
            if ps:
                ps.last_progress_at = end
        sel.last_transition_at = end
        sel.locked_by = None
        sel.lock_heartbeat_at = None
        db.session.commit()
        logger.info(
            json.dumps(
                {
                    "ts": end.isoformat(),
                    "selection_id": sel.id,
                    "status": sel.status,
                }
            ),
            extra={"event": "picker.item.end"},
        )

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
    start_time = datetime.now(timezone.utc)

    # セッション開始ログ
    logger.info(
        json.dumps(
            {
                "ts": start_time.isoformat(),
                "session_id": picker_session_id,
                "account_id": account_id,
            }
        ),
        extra={"event": "picker.session.start"},
    )

    # 1. Lookup picker session and account
    ps, gacc, note = _lookup_session_and_account(picker_session_id, account_id)
    if note == "invalid_session":
        logger.error(
            json.dumps({"ts": start_time.isoformat(), "session_id": picker_session_id, "error": note}),
            extra={"event": "picker.session.error"},
        )
        return {"ok": False, "imported": 0, "dup": 0, "failed": 0, "note": note}
    if note == "already_done":
        logger.info(
            json.dumps({"ts": start_time.isoformat(), "session_id": picker_session_id, "note": note}),
            extra={"event": "picker.session.skip"},
        )
        return {"ok": True, "imported": 0, "dup": 0, "failed": 0, "note": note}
    if note == "account_not_found":
        logger.error(
            json.dumps({"ts": start_time.isoformat(), "session_id": picker_session_id, "error": note}),
            extra={"event": "picker.session.error"},
        )
        return {"ok": False, "imported": 0, "dup": 0, "failed": 0, "note": note}

    # 2. Exchange refresh token for access token
    access_token, note = _exchange_refresh_token(gacc, ps)  # type: ignore[arg-type]
    if note:
        logger.error(
            json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "session_id": picker_session_id, "error": note}),
            extra={"event": "picker.session.error"},
        )
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

        for i, item in enumerate(results):
            media_id = item.get("id")
            if not media_id:
                failed += 1
                continue
            processed_ids.append(media_id)
            
            # 進捗ログ (10件ごとまたは最初と最後)
            total_count = len(results)
            if i == 0 or i == total_count - 1 or (i + 1) % 10 == 0:
                logger.info(
                    json.dumps(
                        {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "session_id": picker_session_id,
                            "progress": f"{i + 1}/{total_count}",
                            "media_id": media_id,
                            "imported": imported,
                            "duplicates": dup,
                            "failed": failed,
                        }
                    ),
                    extra={"event": "picker.session.progress"},
                )
            
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
            if Media.query.filter_by(hash_sha256=dl.sha256, is_deleted=False).first():
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
                source_type="google_photos",
                google_media_id=media_id,
                account_id=account_id,
                local_rel_path=str(out_rel),
                filename=filename or Path(out_rel).name,
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

            process_media_post_import(
                media,
                logger_override=logger,
                request_context={
                    "session_id": picker_session_id,
                    "source": "picker_import_session_replay",
                },
            )

            imported += 1

        db.session.commit()

    stats["processed_ids"] = processed_ids
    ps.set_stats(stats)

    end_time = datetime.now(timezone.utc)
    if imported > 0:
        ps.status = "imported"
        ps.completed_at = end_time
    elif failed > 0:
        ps.status = "error"
    else:  # only duplicates
        ps.status = "imported"
        ps.completed_at = end_time

    db.session.commit()

    # セッション完了ログ
    duration_seconds = (end_time - start_time).total_seconds()
    logger.info(
        json.dumps(
            {
                "ts": end_time.isoformat(),
                "session_id": picker_session_id,
                "account_id": account_id,
                "status": ps.status,
                "duration_seconds": duration_seconds,
                "imported": imported,
                "duplicates": dup,
                "failed": failed,
                "processed_total": len(processed_ids),
            }
        ),
        extra={"event": "picker.session.complete"},
    )

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
