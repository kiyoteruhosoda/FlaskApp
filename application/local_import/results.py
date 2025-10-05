"""取り込み結果の集計ロジック."""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from core.models.celery_task import CeleryTaskRecord, CeleryTaskStatus
from core.models.photo_models import Media, MediaItem, PickerSelection


def build_thumbnail_task_snapshot(
    db,
    session,
    recorded_entries: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "total": 0,
        "completed": 0,
        "pending": 0,
        "failed": 0,
        "entries": [],
        "status": "idle",
    }

    if session is None or session.id is None:
        return summary

    initial: Dict[int, Dict[str, Any]] = {}
    if recorded_entries:
        for entry in recorded_entries:
            if not isinstance(entry, dict):
                continue
            media_id = entry.get("mediaId") or entry.get("media_id")
            if media_id is None:
                continue
            try:
                media_key = int(media_id)
            except (TypeError, ValueError):
                continue
            initial[media_key] = {
                "status": (entry.get("status") or "").lower() or None,
                "ok": entry.get("ok"),
                "notes": entry.get("notes"),
                "retry_scheduled": bool(
                    entry.get("retryScheduled") or entry.get("retry_scheduled")
                ),
                "retry_details": entry.get("retryDetails") or entry.get("retry_details"),
            }

    selection_rows = (
        db.session.query(
            PickerSelection.id,
            PickerSelection.status,
            Media.id.label("media_id"),
            Media.thumbnail_rel_path,
            Media.is_video,
        )
        .outerjoin(MediaItem, PickerSelection.google_media_id == MediaItem.id)
        .outerjoin(Media, Media.google_media_id == MediaItem.id)
        .filter(
            PickerSelection.session_id == session.id,
            PickerSelection.status == "imported",
        )
        .all()
    )

    if not selection_rows:
        return summary

    media_ids = [row.media_id for row in selection_rows if row.media_id is not None]
    celery_records: Dict[int, CeleryTaskRecord] = {}

    if media_ids:
        str_ids = [str(mid) for mid in media_ids]
        records = (
            CeleryTaskRecord.query.filter(
                CeleryTaskRecord.task_name == "thumbnail.retry",
                CeleryTaskRecord.object_type == "media",
                CeleryTaskRecord.object_id.in_(str_ids),
            )
            .order_by(CeleryTaskRecord.id.desc())
            .all()
        )
        for record in records:
            try:
                mid = int(record.object_id) if record.object_id is not None else None
            except (TypeError, ValueError):
                continue
            if mid is None or mid in celery_records:
                continue
            celery_records[mid] = record

    summary["status"] = "progress"

    for row in selection_rows:
        media_id = row.media_id
        if media_id is None:
            continue

        summary["total"] += 1

        recorded = initial.get(media_id, {})
        base_status = (recorded.get("status") or "").lower() or None
        if recorded.get("ok") is False:
            base_status = "error"
        retry_flag = bool(recorded.get("retry_scheduled"))
        note = recorded.get("notes")
        retry_details = recorded.get("retry_details") if recorded else None

        record = celery_records.get(media_id)

        if row.thumbnail_rel_path:
            final_status = "completed"
            retry_flag = False
        else:
            if record is not None:
                if record.status in {
                    CeleryTaskStatus.SCHEDULED,
                    CeleryTaskStatus.QUEUED,
                    CeleryTaskStatus.RUNNING,
                }:
                    final_status = "progress"
                    retry_flag = True
                elif record.status == CeleryTaskStatus.SUCCESS:
                    final_status = "completed"
                    retry_flag = False
                elif record.status in {
                    CeleryTaskStatus.FAILED,
                    CeleryTaskStatus.CANCELED,
                }:
                    final_status = "error"
                else:
                    final_status = base_status or "progress"
            else:
                if base_status == "error":
                    final_status = "error"
                elif retry_flag or base_status in {"progress", "pending", "processing"}:
                    final_status = "progress"
                elif base_status == "completed":
                    final_status = "completed"
                else:
                    final_status = "progress"

        if final_status == "error":
            summary["failed"] += 1
        elif final_status == "completed":
            summary["completed"] += 1
        else:
            summary["pending"] += 1

        entry_payload: Dict[str, Any] = {
            "mediaId": media_id,
            "selectionId": row.id,
            "status": final_status,
            "retryScheduled": retry_flag,
            "thumbnailPath": row.thumbnail_rel_path,
            "notes": note,
            "isVideo": bool(row.is_video),
        }
        if isinstance(retry_details, dict):
            entry_payload["retryDetails"] = retry_details
        if record is not None:
            entry_payload["celeryTaskStatus"] = record.status.value

        summary["entries"].append(entry_payload)

    if summary["failed"] > 0:
        summary["status"] = "error"
    elif summary["pending"] > 0:
        summary["status"] = "progress"
    else:
        summary["status"] = "completed" if summary["total"] > 0 else "idle"

    return summary
