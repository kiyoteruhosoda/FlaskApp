from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import time
from threading import Lock
from typing import Dict, Optional, Tuple, Iterable

from flask import current_app

from ..extensions import db
from core.models.google_account import GoogleAccount
from core.models.picker_session import PickerSession
from core.models.job_sync import JobSync
from core.models.photo_models import (
    PickerSelection,
    MediaItem,
    PhotoMetadata,
    VideoMetadata,
    Media,
)
from ..auth.utils import refresh_google_token, RefreshTokenError, log_requests_and_send


_locks: Dict[str, Lock] = {}
_locks_guard = Lock()


def _get_lock(key: str) -> Lock:
    with _locks_guard:
        lk = _locks.get(key)
        if lk is None:
            lk = Lock()
            _locks[key] = lk
        return lk


def _release_lock(key: str, lk: Lock) -> None:
    with _locks_guard:
        if not lk.locked():
            _locks.pop(key, None)


def _update_picker_session_from_data(ps: PickerSession, data: dict) -> None:
    ps.session_id = data.get("id")
    ps.picker_uri = data.get("pickerUri")
    expire = data.get("expireTime")
    if expire is not None:
        try:
            ps.expire_time = datetime.fromisoformat(expire.replace("Z", "+00:00"))
        except Exception:
            ps.expire_time = None
    if data.get("pollingConfig"):
        ps.polling_config_json = json.dumps(data.get("pollingConfig"))
    if data.get("pickingConfig"):
        ps.picking_config_json = json.dumps(data.get("pickingConfig"))
    if "mediaItemsSet" in data:
        ps.media_items_set = data.get("mediaItemsSet")
    ps.updated_at = datetime.now(timezone.utc)


class PickerSessionService:
    @staticmethod
    def resolve_session_identifier(session_id: str) -> Optional[PickerSession]:
        ps = PickerSession.query.filter_by(session_id=session_id).first()
        if not ps and "/" not in session_id:
            ps = PickerSession.query.filter_by(
                session_id=f"picker_sessions/{session_id}"
            ).first()
        return ps

    # --- Create -----------------------------------------------------------
    @staticmethod
    def create(account: GoogleAccount, title: str) -> Tuple[dict, int]:
        try:
            tokens = refresh_google_token(account)
        except RefreshTokenError as e:
            status = 502 if e.status_code >= 500 else 401
            return {"error": str(e)}, status

        access_token = tokens.get("access_token")
        headers = {"Authorization": f"Bearer {access_token}"}
        body = {"title": title}
        try:
            picker_res = log_requests_and_send(
                "POST",
                "https://photospicker.googleapis.com/v1/sessions",
                json_data=body,
                headers=headers,
                timeout=15,
            )
            picker_res.raise_for_status()
            picker_data = picker_res.json()
        except Exception as e:
            return {"error": "picker_error", "message": str(e)}, 502

        ps = PickerSession(
            account_id=account.id,
            status="pending",
            last_progress_at=datetime.now(timezone.utc),
        )
        db.session.add(ps)
        _update_picker_session_from_data(ps, picker_data)
        db.session.commit()
        return {
            "pickerSessionId": ps.id,
            "sessionId": ps.session_id,
            "pickerUri": ps.picker_uri,
            "expireTime": picker_data.get("expireTime"),
            "pollingConfig": picker_data.get("pollingConfig"),
            "pickingConfig": picker_data.get("pickingConfig"),
            "mediaItemsSet": picker_data.get("mediaItemsSet"),
        }, 200

    # --- Status -----------------------------------------------------------
    @staticmethod
    def status(ps: PickerSession) -> dict:
        account = GoogleAccount.query.get(ps.account_id)
        selected = ps.selected_count
        if selected is None and account and account.status == "active" and ps.session_id:
            try:
                tokens = refresh_google_token(account)
                access_token = tokens.get("access_token")
                res = log_requests_and_send(
                    "GET",
                    f"https://photospicker.googleapis.com/v1/sessions/{ps.session_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=15,
                )
                res.raise_for_status()
                data = res.json()
                selected = (
                    data.get("selectedCount")
                    or data.get("selectedMediaCount")
                    or data.get("selectedMediaItems")
                )
                _update_picker_session_from_data(ps, data)
            except Exception:
                selected = None
        ps.selected_count = selected
        ps.last_polled_at = datetime.now(timezone.utc)
        ps.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        return {
            "status": ps.status,
            "selectedCount": ps.selected_count,
            "lastPolledAt": ps.last_polled_at.isoformat().replace("+00:00", "Z"),
            "serverTimeRFC1123": datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT'),
            "sessionId": ps.session_id,
            "pickerUri": ps.picker_uri,
            "expireTime": ps.expire_time.isoformat().replace("+00:00", "Z") if ps.expire_time else None,
            "pollingConfig": json.loads(ps.polling_config_json) if ps.polling_config_json else None,
            "pickingConfig": json.loads(ps.picking_config_json) if ps.picking_config_json else None,
            "mediaItemsSet": ps.media_items_set,
        }

    # --- Media Items ------------------------------------------------------
    @staticmethod
    def media_items(session_id: str) -> Tuple[dict, int]:
        lock = _get_lock(session_id)
        if not lock.acquire(blocking=False):
            return {"error": "busy"}, 409
        try:
            return PickerSessionService._media_items_locked(session_id)
        finally:
            lock.release()
            _release_lock(session_id, lock)

    @staticmethod
    def _media_items_locked(session_id: str) -> Tuple[dict, int]:
        ps = PickerSession.query.filter_by(session_id=session_id).first()
        if not ps or ps.status not in ("pending", "processing"):
            return {"error": "not_found"}, 404
        PickerSessionService._mark_processing(ps)
        try:
            headers = PickerSessionService._auth_headers(ps.account_id)
            if headers is None:
                return {"error": "invalid_account"}, 404

            PickerSessionService._refresh_session_snapshot(ps, headers, session_id)
            saved, dup, new_pmis = PickerSessionService._fetch_and_store_items(
                ps, headers, session_id
            )
            PickerSessionService._enqueue_new_items(ps, new_pmis)
            return {"saved": saved, "duplicates": dup, "nextCursor": None}, 200
        except Exception as e:
            db.session.rollback()
            now = datetime.now(timezone.utc)
            ps.status = "pending"
            ps.updated_at = now
            ps.last_progress_at = now
            db.session.commit()
            raise

    @staticmethod
    def _mark_processing(ps: PickerSession) -> None:
        ps.status = "processing"
        ps.updated_at = datetime.now(timezone.utc)
        ps.last_progress_at = ps.updated_at
        db.session.commit()

    @staticmethod
    def _auth_headers(account_id: int) -> Optional[dict]:
        account = GoogleAccount.query.get(account_id)
        if not account:
            return None
        try:
            tokens = refresh_google_token(account)
        except RefreshTokenError as e:
            status = 502 if e.status_code >= 500 else 401
            raise RuntimeError(json.dumps({"error": str(e), "status": status}))
        return {"Authorization": f"Bearer {tokens.get('access_token')}"}

    @staticmethod
    def _refresh_session_snapshot(ps: PickerSession, headers: dict, session_id: str) -> None:
        sess_res = log_requests_and_send(
            "GET",
            f"https://photospicker.googleapis.com/v1/sessions/{session_id}",
            headers=headers,
            timeout=15,
        )
        sess_res.raise_for_status()
        sess_data = sess_res.json()
        _update_picker_session_from_data(ps, sess_data)
        db.session.commit()

    @staticmethod
    def _fetch_and_store_items(ps: PickerSession, headers: dict, session_id: str) -> Tuple[int, int, Iterable[PickerSelection]]:
        params = {"sessionId": session_id, "pageSize": 100}
        saved = 0
        dup = 0
        new_pmis = []
        while True:
            picker_data = PickerSessionService._fetch_items_page(headers, params)
            items = picker_data.get("mediaItems") or []
            page_saved, page_dup, page_new = PickerSessionService._save_media_items(ps, items)
            saved += page_saved
            dup += page_dup
            new_pmis.extend(page_new)
            cursor = picker_data.get("nextPageToken")
            if cursor:
                params["pageToken"] = cursor
                continue
            break
        return saved, dup, new_pmis

    @staticmethod
    def _fetch_items_page(headers: dict, params: dict) -> dict:
        while True:
            try:
                res = log_requests_and_send(
                    "GET",
                    "https://photospicker.googleapis.com/v1/mediaItems",
                    params=params,
                    headers=headers,
                    timeout=15,
                )
            except Exception as fetch_exc:
                raise RuntimeError(f"mediaItems fetch failed: {fetch_exc}")

            if getattr(res, "status_code", 200) == 429:
                time.sleep(1)
                continue
            res.raise_for_status()
            return res.json()

    @staticmethod
    def _save_media_items(ps: PickerSession, items: Iterable[dict]) -> Tuple[int, int, Iterable[PickerSelection]]:
        saved = 0
        dup = 0
        new_pmis = []
        for item in items:
            result = PickerSessionService._save_single_item(ps, item)
            if result is None:
                dup += 1
                continue
            pmi = result
            saved += 1
            new_pmis.append(pmi)
        return saved, dup, new_pmis

    @staticmethod
    def _save_single_item(ps: PickerSession, item: dict) -> Optional[PickerSelection]:
        item_id = item.get("id")
        if not item_id:
            return None
        if Media.query.filter_by(google_media_id=item_id, account_id=ps.account_id).first() or \
                PickerSelection.query.filter_by(session_id=ps.id, google_media_id=item_id).first():
            current_app.logger.info(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "session_id": ps.session_id,
                        "google_media_id": item_id,
                    }
                ),
                extra={"event": "picker.mediaItems.duplicate"},
            )
            return None

        mi = MediaItem.query.get(item_id) or MediaItem(id=item_id, type="TYPE_UNSPECIFIED")
        pmi = PickerSelection(session_id=ps.id, google_media_id=item_id, status="pending")

        ct = item.get("createTime")
        if ct:
            try:
                pmi.create_time = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            except Exception:
                pmi.create_time = None

        mf_dict = item.get("mediaFile") or {}
        if isinstance(mf_dict, dict):
            mi.mime_type = mf_dict.get("mimeType")
            mi.filename = mf_dict.get("filename")
            pmi.base_url = mf_dict.get("baseUrl")
            if pmi.base_url:
                now = datetime.now(timezone.utc)
                pmi.base_url_fetched_at = now
                pmi.base_url_valid_until = now + timedelta(hours=1)
            meta = mf_dict.get("mediaFileMetadata") or {}
        else:
            meta = {}

        PickerSessionService._apply_meta(mi, pmi, meta)

        pmi.updated_at = datetime.now(timezone.utc)
        db.session.add(mi)
        db.session.add(pmi)
        db.session.flush()
        return pmi

    @staticmethod
    def _apply_meta(mi: MediaItem, pmi: PickerSelection, meta: dict) -> None:
        width = meta.get("width")
        height = meta.get("height")
        if width is not None:
            try:
                mi.width = int(width)
            except Exception:
                mi.width = None
        if height is not None:
            try:
                mi.height = int(height)
            except Exception:
                mi.height = None
        mi.camera_make = meta.get("cameraMake")
        mi.camera_model = meta.get("cameraModel")

        photo_meta = meta.get("photoMetadata") or {}
        video_meta = meta.get("videoMetadata") or {}

        if photo_meta:
            pm = mi.photo_metadata or PhotoMetadata()
            pm.focal_length = photo_meta.get("focalLength")
            pm.aperture_f_number = photo_meta.get("apertureFNumber")
            pm.iso_equivalent = photo_meta.get("isoEquivalent")
            pm.exposure_time = photo_meta.get("exposureTime")
            mi.photo_metadata = pm
            mi.type = "PHOTO"

        if video_meta:
            vm = mi.video_metadata or VideoMetadata()
            vm.fps = video_meta.get("fps")
            vm.processing_status = video_meta.get("processingStatus")
            mi.video_metadata = vm
            mi.type = "VIDEO"

    @staticmethod
    def _enqueue_new_items(ps: PickerSession, new_pmis: Iterable[PickerSelection]) -> None:
        ps.status = "imported"
        now = datetime.now(timezone.utc)
        ps.updated_at = now
        ps.last_progress_at = now
        for pmi in new_pmis:
            pmi.status = "enqueued"
            pmi.enqueued_at = now
        db.session.commit()
        # Late import to allow tests to monkeypatch via picker_session module
        from webapp.api import picker_session as ps_module  # type: ignore
        for pmi in new_pmis:
            ps_module.enqueue_picker_import_item(pmi.id, ps.id)

    # --- Enqueue Import ---------------------------------------------------
    @staticmethod
    def enqueue_import(ps: PickerSession, account_id_in: Optional[int]) -> Tuple[dict, int]:
        if account_id_in and ps.account_id != account_id_in:
            return {"error": "not_found"}, 404
        if ps.status in ("imported", "canceled", "expired", "error"):
            return {"error": "already_done"}, 409

        existing = (
            JobSync.query
            .filter(
                JobSync.target == "picker_import",
                JobSync.session_id == ps.id,
                JobSync.status.in_(("queued", "running")),
            )
            .order_by(JobSync.started_at.desc().nullslast())
            .first()
        )
        if existing:
            return {"error": "already_enqueued", "jobId": existing.id}, 409

        job, task_id = PickerSessionService._create_job(ps, account_id_in or ps.account_id)
        try:
            PickerSessionService._publish_celery(ps, job, task_id)
        except Exception as e:  # pragma: no cover - publishing failure path
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
            job.stats_json = json.dumps({"celery_task_id": task_id, "error": str(e)})
            ps.status = "error"
            ps.last_progress_at = datetime.now(timezone.utc)
            db.session.commit()
            return {"error": "enqueue_failed"}, 500

        return {"enqueued": True, "jobId": job.id, "celeryTaskId": task_id, "status": "queued"}, 202

    @staticmethod
    def _create_job(ps: PickerSession, account_id: int) -> Tuple[JobSync, str]:
        task_id = uuid4().hex
        job = JobSync(
            target="picker_import",
            account_id=account_id,
            session_id=ps.id,
            started_at=None,
            finished_at=None,
            stats_json=json.dumps({"celery_task_id": task_id, "selected": getattr(ps, "selected_count", 0)}),
        )
        db.session.add(job)
        stats = ps.stats()
        stats["celery_task_id"] = task_id
        stats["job_id"] = None
        ps.set_stats(stats)
        ps.status = "enqueued"
        ps.last_progress_at = datetime.now(timezone.utc)
        db.session.flush()
        stats["job_id"] = job.id
        ps.set_stats(stats)
        db.session.commit()
        return job, task_id

    @staticmethod
    def _publish_celery(ps: PickerSession, job: JobSync, task_id: str) -> None:
        # Placeholder for Celery integration
        print("dummy")

    # --- Finish -----------------------------------------------------------
    @staticmethod
    def finish(ps: PickerSession, status: str) -> Tuple[dict, int]:
        now = datetime.now(timezone.utc)
        ps.status = status
        ps.last_progress_at = now
        ps.updated_at = now

        counts = dict(
            db.session.query(
                PickerSelection.status, db.func.count(PickerSelection.id)
            )
            .filter(PickerSelection.session_id == ps.id)
            .group_by(PickerSelection.status)
            .all()
        )

        job = (
            JobSync.query.filter_by(target="picker_import", session_id=ps.id)
            .order_by(JobSync.started_at.desc().nullslast())
            .first()
        )
        if job:
            job.finished_at = now
            if status == "imported":
                job.status = "success"
            elif status == "error":
                job.status = "failed"
            else:
                job.status = status
            stats = json.loads(job.stats_json or "{}")
            stats["countsByStatus"] = counts
            job.stats_json = json.dumps(stats)

        db.session.commit()
        return {"status": status, "countsByStatus": counts}, 200
