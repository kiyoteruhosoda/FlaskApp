from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import time
from threading import Lock
from typing import Dict, Optional, Tuple, Iterable, List, Any, Sequence
from uuid import uuid4

from flask import current_app

from .pagination import PaginationParams, Paginator
from ..extensions import db
from sqlalchemy import or_, func, insert as sa_insert
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from core.models.google_account import GoogleAccount
from core.models.picker_session import PickerSession
from core.models.job_sync import JobSync
from core.models.celery_task import CeleryTaskRecord, CeleryTaskStatus
from core.models.photo_models import (
    PickerSelection,
    MediaItem,
    PhotoMetadata,
    VideoMetadata,
    Media,
)
from core.models.log import Log
from ..auth.utils import refresh_google_token, RefreshTokenError, log_requests_and_send
from core.tasks.local_import import build_thumbnail_task_snapshot
from .concurrency import (
    ConcurrencyLimitExceeded,
    create_limiter,
)
from core.time import utc_now_isoformat


_locks: Dict[str, Lock] = {}
_locks_guard = Lock()

_media_items_concurrency = create_limiter(
    "PICKER_MEDIA_ITEMS", retry_suffix="_RETRY_DELAY_SECONDS"
)


def _acquire_media_items_slot() -> bool:
    return _media_items_concurrency.acquire()


def _release_media_items_slot() -> None:
    _media_items_concurrency.release()


def _coerce_selected_count(raw: object) -> Optional[int]:
    """Convert picker API selected count payloads into an integer count."""

    if raw is None:
        return None

    if isinstance(raw, bool):  # bool is a subclass of int
        return int(raw)

    if isinstance(raw, int):
        return raw

    if isinstance(raw, (list, tuple, set)):
        return len(raw)

    if isinstance(raw, str):
        candidate = raw.strip()
        if not candidate:
            return None
        if candidate.isdigit():
            return int(candidate)
        try:
            # Fallback for strings such as "3.0"
            return int(float(candidate))
        except (TypeError, ValueError):
            return None

    try:
        return int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


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


def _isoformat(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    value = dt
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _normalize_log_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _isoformat(value)
    return value


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
    def _normalize_selection_counts(raw_counts: Dict[str, int]) -> Dict[str, int]:
        """Normalize selection status counters into canonical keys."""

        if not raw_counts:
            return {}

        aliases = {
            "duplicate": "dup",
            "duplicates": "dup",
        }

        normalized: Dict[str, int] = {}
        for raw_key, raw_value in raw_counts.items():
            if raw_value in (None, ""):
                continue

            key = (raw_key or "").strip()
            if not key:
                continue

            canonical_key = aliases.get(key.lower(), key.lower())

            try:
                count_value = int(raw_value)
            except (TypeError, ValueError):
                continue

            normalized[canonical_key] = normalized.get(canonical_key, 0) + count_value

        return normalized

    @staticmethod
    def _determine_completion_status(counts: Dict[str, int]) -> Optional[str]:
        if not counts:
            return None

        normalized = PickerSessionService._normalize_selection_counts(counts)

        pending_statuses = ["pending", "enqueued", "running"]
        if any(normalized.get(status, 0) > 0 for status in pending_statuses):
            return None

        failed_count = normalized.get("failed", 0)
        imported_count = normalized.get("imported", 0)
        dup_count = normalized.get("dup", 0)
        skipped_count = normalized.get("skipped", 0)

        only_duplicates = (
            imported_count == 0
            and failed_count == 0
            and dup_count > 0
            and skipped_count == 0
        )

        only_skipped = (
            imported_count == 0
            and failed_count == 0
            and skipped_count > 0
            and dup_count == 0
        )

        if failed_count > 0:
            return "error"

        if imported_count > 0:
            return "imported"

        if only_duplicates:
            return "imported"

        if only_skipped:
            return "pending"

        total = sum(normalized.values())
        if total > 0:
            return "pending"

        return None

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
        account = GoogleAccount.query.get(ps.account_id) if ps.account_id else None
        selected = ps.selected_count

        counts_query = (
            db.session.query(
                PickerSelection.status,
                db.func.count(PickerSelection.id)
            )
            .filter(PickerSelection.session_id == ps.id)
            .group_by(PickerSelection.status)
            .all()
        )
        raw_counts: Dict[str, int] = {row[0]: row[1] for row in counts_query}
        counts = PickerSessionService._normalize_selection_counts(raw_counts)

        if (selected is None or selected == 0) and counts:
            selected = sum(counts.values())

        if selected is None and account and account.status == "active" and ps.session_id and not counts:
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
                selected = _coerce_selected_count(
                    data.get("selectedCount")
                    or data.get("selectedMediaCount")
                    or data.get("selectedMediaItems")
                )
                _update_picker_session_from_data(ps, data)
            except Exception:
                selected = None

        ps.selected_count = selected
        now = datetime.now(timezone.utc)
        ps.last_polled_at = now
        ps.updated_at = now

        status_log_context = {
            "ts": now.isoformat(),
            "picker_session_id": ps.id,
            "session_id": ps.session_id,
            "status_before": ps.status,
            "selected_count": ps.selected_count,
            "counts": counts,
        }
        current_app.logger.info(
            json.dumps(status_log_context, default=str),
            extra={"event": "pickerSession.status.summary"},
        )

        pending_statuses = ("pending", "enqueued", "running")
        has_pending = any(counts.get(status, 0) > 0 for status in pending_statuses)

        stats = ps.stats() if hasattr(ps, "stats") else {}
        if not isinstance(stats, dict):
            stats = {}

        is_local_import = ps.account_id is None

        thumbnail_snapshot: Dict[str, Any] | None = None
        thumbnails_pending = False
        thumbnails_failed = False

        if is_local_import:
            recorded_entries = None
            raw_thumb_stats = stats.get("thumbnails")
            if isinstance(raw_thumb_stats, dict):
                recorded_entries = raw_thumb_stats.get("entries")
            thumbnail_snapshot = build_thumbnail_task_snapshot(ps, recorded_entries)
            if not isinstance(thumbnail_snapshot, dict):
                thumbnail_snapshot = None
            if thumbnail_snapshot:
                thumbnails_pending = thumbnail_snapshot.get("status") == "progress"
                thumbnails_failed = thumbnail_snapshot.get("status") == "error"

        status_changed = False
        if ps.status not in {"canceled", "failed"}:
            if thumbnails_failed and ps.status != "error":
                current_app.logger.info(
                    json.dumps(
                        {
                            **status_log_context,
                            "status_after": "error",
                            "reason": "thumbnail_generation_failed",
                        },
                        default=str,
                    ),
                    extra={"event": "pickerSession.status.thumbnailError"},
                )
                ps.status = "error"
                ps.last_progress_at = now
                ps.updated_at = now
                status_changed = True
            elif has_pending or thumbnails_pending:
                if ps.status != "processing":
                    current_app.logger.info(
                        json.dumps(
                            {
                                **status_log_context,
                                "status_after": "processing",
                                "reason": "pending_items_present",
                            },
                            default=str,
                        ),
                        extra={"event": "pickerSession.status.forceProcessing"},
                    )
                    ps.status = "processing"
                    ps.last_progress_at = now
                    ps.updated_at = now
                    status_changed = True
            elif ps.status in ("processing", "importing", "error", "failed", "pending", "imported"):
                new_status = PickerSessionService._determine_completion_status(counts)
                if new_status and ps.status != new_status:
                    current_app.logger.info(
                        json.dumps(
                            {
                                **status_log_context,
                                "status_after": new_status,
                                "reason": "no_pending_and_completion_status_resolved",
                            },
                            default=str,
                        ),
                        extra={"event": "pickerSession.status.transition"},
                    )
                    ps.status = new_status
                    ps.last_progress_at = now
                    ps.updated_at = now
                    status_changed = True

        stats_changed = False
        if is_local_import:
            if not thumbnail_snapshot:
                thumbnail_snapshot = {
                    "status": "idle",
                    "total": 0,
                    "completed": 0,
                    "pending": 0,
                    "failed": 0,
                    "entries": [],
                }
            else:
                thumbnail_snapshot.setdefault("total", 0)
                thumbnail_snapshot.setdefault("completed", 0)
                thumbnail_snapshot.setdefault("pending", 0)
                thumbnail_snapshot.setdefault("failed", 0)
                thumbnail_snapshot.setdefault("entries", [])

            pending_remaining = sum(counts.get(status, 0) for status in pending_statuses)
            import_total = sum(counts.values()) if counts else 0
            import_success = counts.get("imported", 0)
            dup_count = counts.get("dup", 0)
            manual_skipped_count = counts.get("skipped", 0)
            import_skipped = dup_count + manual_skipped_count
            import_failed = counts.get("failed", 0)
            only_manual_skipped = (
                import_success == 0
                and import_failed == 0
                and manual_skipped_count > 0
                and dup_count == 0
            )
            only_duplicates = (
                import_success == 0
                and import_failed == 0
                and dup_count > 0
                and manual_skipped_count == 0
            )

            import_task_status = "canceled" if stats.get("cancel_requested") else None
            if import_task_status is None:
                if pending_remaining > 0 or thumbnails_pending:
                    import_task_status = "progress"
                elif import_failed > 0:
                    import_task_status = "error"
                elif import_success > 0 or only_duplicates:
                    import_task_status = "completed"
                elif only_manual_skipped or import_total > 0:
                    import_task_status = "pending"
                else:
                    import_task_status = "idle"

            tasks_payload: List[Dict[str, Any]] = [
                {
                    "key": "import",
                    "label": "File Import",
                    "status": import_task_status,
                    "counts": {
                        "total": import_total,
                        "success": import_success,
                        "skipped": import_skipped,
                        "failed": import_failed,
                        "pending": pending_remaining,
                    },
                }
            ]

            if thumbnail_snapshot.get("total") or thumbnail_snapshot.get("status") not in {None, "idle"}:
                tasks_payload.append(
                    {
                        "key": "thumbnails",
                        "label": "Thumbnail Generation",
                        "status": thumbnail_snapshot.get("status"),
                        "counts": {
                            "total": thumbnail_snapshot.get("total"),
                            "completed": thumbnail_snapshot.get("completed"),
                            "pending": thumbnail_snapshot.get("pending"),
                            "failed": thumbnail_snapshot.get("failed"),
                        },
                        "entries": thumbnail_snapshot.get("entries"),
                    }
                )

            if stats.get("tasks") != tasks_payload:
                stats["tasks"] = tasks_payload
                stats_changed = True

            if stats.get("thumbnails") != thumbnail_snapshot:
                stats["thumbnails"] = thumbnail_snapshot
                stats_changed = True

            stage_before = stats.get("stage")
            stage_after = stage_before
            if stage_before == "expanding":
                if pending_remaining > 0 or thumbnails_pending or only_manual_skipped:
                    stage_after = "progress"
                elif thumbnails_failed:
                    stage_after = "error"
            elif stage_before not in {"canceled"}:
                if thumbnails_failed:
                    stage_after = "error"
                elif (
                    pending_remaining > 0
                    or thumbnails_pending
                    or only_manual_skipped
                ):
                    stage_after = "progress"
                else:
                    stage_after = "completed"
            if stage_after and stage_after != stage_before:
                stats["stage"] = stage_after
                stats_changed = True

        if stats_changed:
            ps.set_stats(stats)

        db.session.commit()

        if (ps.selected_count in (None, 0)) and counts:
            selected_count_response = sum(counts.values())
        else:
            selected_count_response = ps.selected_count or 0

        response_status = ps.status
        if is_local_import and isinstance(stats, dict):
            stage = stats.get("stage")
            if stage == "expanding" and ps.status not in {"canceled", "error", "failed", "expired"}:
                response_status = "expanding"

        return {
            "status": response_status,
            "selectedCount": selected_count_response,
            "lastPolledAt": ps.last_polled_at.isoformat().replace("+00:00", "Z"),
            "server_time": utc_now_isoformat(),
            "sessionId": ps.session_id,
            "pickerUri": ps.picker_uri,
            "expireTime": ps.expire_time.isoformat().replace("+00:00", "Z") if ps.expire_time else None,
            "pollingConfig": json.loads(ps.polling_config_json) if ps.polling_config_json else None,
            "pickingConfig": json.loads(ps.picking_config_json) if ps.picking_config_json else None,
            "mediaItemsSet": ps.media_items_set,
            "counts": counts,
            "accountId": ps.account_id,
            "accountEmail": getattr(account, "email", None),
            "isLocalImport": is_local_import,
            "lastProgressAt": ps.last_progress_at.isoformat().replace("+00:00", "Z") if ps.last_progress_at else None,
            "createdAt": ps.created_at.isoformat().replace("+00:00", "Z") if ps.created_at else None,
            "stats": stats,
        }

    @staticmethod
    def selection_details(
        ps: PickerSession,
        params: Optional[PaginationParams] = None,
        *,
        status_filters: Optional[Sequence[str]] = None,
        search_term: Optional[str] = None,
    ) -> dict:
        """Return detailed status of each picker selection for a session."""

        # デフォルトページングパラメータ
        if params is None:
            params = PaginationParams(page_size=200)

        # ベースクエリ（効率的なJOIN）
        base_query = (
            db.session.query(PickerSelection)
            .filter(PickerSelection.session_id == ps.id)
        )

        normalized_status_filters: List[str] = []
        if status_filters:
            seen = set()
            for raw_value in status_filters:
                if not raw_value:
                    continue
                value = raw_value.strip().lower()
                if not value or value in seen:
                    continue
                seen.add(value)
            normalized_status_filters = sorted(seen)

        if normalized_status_filters:
            base_query = base_query.filter(PickerSelection.status.in_(normalized_status_filters))

        normalized_search: Optional[str] = None
        if search_term:
            normalized_search = search_term.strip()
            if normalized_search:
                normalized_search = normalized_search.lower()

        if normalized_search:
            like_pattern = f"%{normalized_search}%"
            base_query = base_query.outerjoin(
                MediaItem,
                PickerSelection.google_media_id == MediaItem.id,
            ).filter(
                or_(
                    func.lower(PickerSelection.local_filename).like(like_pattern),
                    func.lower(PickerSelection.google_media_id).like(like_pattern),
                    func.lower(MediaItem.filename).like(like_pattern),
                )
            )

        # ページング処理
        paginated_result = Paginator.paginate_query(
            query=base_query,
            params=params,
            id_column=PickerSelection.id,
            count_total=not params.use_cursor
        )
        
        # ページング結果からgoogle_media_idを取得
        selection_items = paginated_result.items
        google_media_ids = [sel.google_media_id for sel in selection_items if sel.google_media_id]
        
        # 一括でMediaItemを取得
        media_items = {}
        media_map = {}
        if google_media_ids:
            media_items_query = db.session.query(MediaItem).filter(MediaItem.id.in_(google_media_ids)).all()
            media_items = {mi.id: mi for mi in media_items_query}

            media_query = db.session.query(Media).filter(Media.google_media_id.in_(google_media_ids))
            if ps.account_id is None:
                media_query = media_query.filter(Media.account_id.is_(None))
            else:
                media_query = media_query.filter(Media.account_id == ps.account_id)
            media_records = media_query.all()
            media_map = {
                media.google_media_id: media
                for media in media_records
                if media.google_media_id
            }
        
        # 選択アイテムのシリアライザ関数
        def serialize_selection(sel):
            mi = media_items.get(sel.google_media_id) if sel.google_media_id else None
            media = media_map.get(sel.google_media_id) if sel.google_media_id else None

            return {
                "id": sel.id,
                "googleMediaId": sel.google_media_id,
                "filename": sel.local_filename or (mi.filename if mi else None),  # ローカルインポート用にlocal_filenameを優先
                "status": sel.status,
                "attempts": sel.attempts,
                "error": sel.error_msg,
                "enqueuedAt": sel.enqueued_at.isoformat().replace("+00:00", "Z") if sel.enqueued_at else None,
                "startedAt": sel.started_at.isoformat().replace("+00:00", "Z") if sel.started_at else None,
                "finishedAt": sel.finished_at.isoformat().replace("+00:00", "Z") if sel.finished_at else None,
                "mediaId": media.id if media else None,
            }
        
        # 選択状況の集計（全体）
        counts_query = (
            db.session.query(
                PickerSelection.status,
                db.func.count(PickerSelection.id)
            )
            .filter(PickerSelection.session_id == ps.id)
            .group_by(PickerSelection.status)
            .all()
        )
        raw_counts: Dict[str, int] = {row[0]: row[1] for row in counts_query}
        counts = PickerSessionService._normalize_selection_counts(raw_counts)
        
        # アイテムのシリアライズ
        selections = [serialize_selection(sel) for sel in paginated_result.items]
        
        # PickerSessionのステータス自動更新ロジック
        if ps.status in ("processing", "importing", "error", "failed") and counts:
            new_status = PickerSessionService._determine_completion_status(counts)
            if new_status and ps.status != new_status:
                ps.status = new_status
                now = datetime.now(timezone.utc)
                if hasattr(ps, "completed_at"):
                    ps.completed_at = now
                ps.last_progress_at = now
                ps.updated_at = now
                db.session.commit()
        
        # レスポンス構築
        result = {
            "selections": selections,
            "counts": counts,
            "pagination": {
                "hasNext": paginated_result.has_next,
                "hasPrev": paginated_result.has_prev,
            }
        }
        
        # ページング情報の追加
        if paginated_result.next_cursor:
            result["pagination"]["nextCursor"] = paginated_result.next_cursor
        if paginated_result.prev_cursor:
            result["pagination"]["prevCursor"] = paginated_result.prev_cursor
        if paginated_result.current_page:
            result["pagination"]["currentPage"] = paginated_result.current_page
        if paginated_result.total_pages:
            result["pagination"]["totalPages"] = paginated_result.total_pages
        if paginated_result.total_count is not None:
            result["pagination"]["totalCount"] = paginated_result.total_count

        return result

    @staticmethod
    def _selection_error_logs(selection: PickerSelection, limit: int = 50) -> List[dict]:
        """Return parsed log entries associated with *selection*."""

        search_numeric = f'"selection_id": {selection.id}'
        search_string = f'"selection_id": "{selection.id}"'

        rows = (
            Log.query.filter(
                or_(
                    Log.message.contains(search_numeric),
                    Log.message.contains(search_string),
                )
            )
            .order_by(Log.id.desc())
            .limit(max(1, min(limit, 200)))
            .all()
        )

        entries: List[dict] = []

        for row in rows:
            try:
                payload = json.loads(row.message)
            except Exception:
                payload = {"message": row.message}

            extras = payload.get("_extra") or {}
            selection_match = False

            candidate = extras.get("selection_id")
            if candidate == selection.id or str(candidate) == str(selection.id):
                selection_match = True

            if not selection_match:
                candidate = payload.get("selection_id")
                if candidate == selection.id or str(candidate) == str(selection.id):
                    selection_match = True

            if not selection_match:
                continue

            normalized_extras = {
                key: _normalize_log_value(value)
                for key, value in extras.items()
            }

            error_details_raw = normalized_extras.get("error_details")
            if isinstance(error_details_raw, str):
                try:
                    error_details = json.loads(error_details_raw)
                except Exception:
                    error_details = error_details_raw
            else:
                error_details = error_details_raw

            if error_details is not None:
                normalized_extras["error_details"] = error_details

            entry = {
                "id": row.id,
                "level": row.level,
                "event": row.event,
                "createdAt": _isoformat(row.created_at),
                "message": payload.get("message"),
                "extra": normalized_extras,
            }

            if error_details is not None:
                entry["errorDetails"] = error_details

            status_value = payload.get("status")
            if status_value is not None:
                entry["status"] = status_value

            if row.trace:
                entry["trace"] = row.trace

            entries.append(entry)

        entries.reverse()
        return entries

    @staticmethod
    def selection_error_payload(ps: PickerSession, selection_id: int) -> Optional[dict]:
        """Return error payload for a selection belonging to *ps*."""

        selection = (
            PickerSelection.query.filter_by(id=selection_id, session_id=ps.id)
            .first()
        )
        if not selection:
            return None

        selection_payload = {
            "id": selection.id,
            "sessionDbId": selection.session_id,
            "googleMediaId": selection.google_media_id,
            "filename": selection.local_filename
            or (selection.media_item.filename if selection.media_item else None),
            "status": selection.status,
            "attempts": selection.attempts,
            "error": selection.error_msg,
            "localFilePath": selection.local_file_path,
            "enqueuedAt": _isoformat(selection.enqueued_at),
            "startedAt": _isoformat(selection.started_at),
            "finishedAt": _isoformat(selection.finished_at),
            "createTime": _isoformat(selection.create_time),
        }

        session_payload = {
            "id": ps.id,
            "sessionId": ps.session_id,
            "status": ps.status,
            "accountId": ps.account_id,
        }

        logs = PickerSessionService._selection_error_logs(selection)

        return {
            "session": session_payload,
            "selection": selection_payload,
            "logs": logs,
        }
    # --- Media Items ------------------------------------------------------
    @staticmethod
    def media_items(session_id: str, cursor: Optional[str] = None) -> Tuple[dict, int]:
        try:
            with _media_items_concurrency:
                lock = _get_lock(session_id)
                if not lock.acquire(blocking=False):
                    return {"error": "busy"}, 409
                try:
                    return PickerSessionService._media_items_locked(session_id, cursor)
                finally:
                    lock.release()
                    _release_lock(session_id, lock)
        except ConcurrencyLimitExceeded as exc:
            retry_after = exc.retry_after
            return {
                "error": "rate_limited",
                "retryAfter": retry_after,
            }, 429

    @staticmethod
    def _media_items_locked(session_id: str, cursor: Optional[str]) -> Tuple[dict, int]:
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
                ps, headers, session_id, cursor
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
    def _fetch_and_store_items(ps: PickerSession, headers: dict, session_id: str, cursor: Optional[str]) -> Tuple[int, int, Iterable[PickerSelection]]:
        params = {"sessionId": session_id, "pageSize": 100}
        if cursor:
            params["pageToken"] = cursor
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
            if getattr(pmi, "status", None) == "dup":
                dup += 1
                continue
            saved += 1
            new_pmis.append(pmi)
        return saved, dup, new_pmis

    @staticmethod
    def _save_single_item(ps: PickerSession, item: dict) -> Optional[PickerSelection]:
        item_id = item.get("id")
        if not item_id:
            return None
        
        # 既存のメディアまたは他のセッションでの選択をチェック
        existing_media = (
            Media.query.filter_by(
                google_media_id=item_id, account_id=ps.account_id, is_deleted=False
            ).first()
        )
        existing_selection = PickerSelection.query.filter_by(session_id=ps.id, google_media_id=item_id).first()
        
        # 現在のセッションで既に存在する場合は何もしない
        if existing_selection:
            return None
            
        # 重複判定
        is_duplicate = existing_media is not None
        status = "dup" if is_duplicate else "pending"
        
        if is_duplicate:
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

        mi = MediaItem.query.get(item_id) or MediaItem(id=item_id, type="TYPE_UNSPECIFIED")
        pmi = PickerSelection(session_id=ps.id, google_media_id=item_id, status=status)

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

        now = datetime.now(timezone.utc)
        pmi.created_at = pmi.created_at or now
        pmi.updated_at = now

        db.session.add(mi)

        selection_table = PickerSelection.__table__
        selection_values = {
            "session_id": pmi.session_id,
            "google_media_id": pmi.google_media_id,
            "status": pmi.status,
            "create_time": pmi.create_time,
            "base_url": pmi.base_url,
            "base_url_fetched_at": pmi.base_url_fetched_at,
            "base_url_valid_until": pmi.base_url_valid_until,
            "created_at": pmi.created_at,
            "updated_at": pmi.updated_at,
        }

        bind = db.session.bind
        dialect_name = bind.dialect.name if bind is not None else ""
        statement = None

        if dialect_name == "mysql":
            insert_stmt = mysql_insert(selection_table).values(**selection_values)
            update_values = {
                "updated_at": insert_stmt.inserted.updated_at,
                "base_url": insert_stmt.inserted.base_url,
                "base_url_fetched_at": insert_stmt.inserted.base_url_fetched_at,
                "base_url_valid_until": insert_stmt.inserted.base_url_valid_until,
            }
            if is_duplicate:
                update_values["status"] = "dup"
            else:
                update_values["status"] = insert_stmt.inserted.status
            statement = insert_stmt.on_duplicate_key_update(**update_values)
        elif dialect_name == "sqlite":
            insert_stmt = sqlite_insert(selection_table).values(**selection_values)
            excluded = insert_stmt.excluded
            update_values = {
                "updated_at": excluded.updated_at,
                "base_url": excluded.base_url,
                "base_url_fetched_at": excluded.base_url_fetched_at,
                "base_url_valid_until": excluded.base_url_valid_until,
            }
            if is_duplicate:
                update_values["status"] = "dup"
            else:
                update_values["status"] = excluded.status
            statement = insert_stmt.on_conflict_do_update(
                index_elements=[selection_table.c.session_id, selection_table.c.google_media_id],
                set_=update_values,
            )
        else:
            statement = sa_insert(selection_table).values(**selection_values)

        try:
            db.session.execute(statement)
        except IntegrityError:
            # 他のトランザクションが先に同一キーで登録した場合は既存行をdup扱いに更新
            existing = PickerSelection.query.filter_by(
                session_id=ps.id, google_media_id=item_id
            ).with_for_update(nowait=False).first()
            if existing:
                if is_duplicate and existing.status != "dup":
                    existing.status = "dup"
                    existing.updated_at = now
                db.session.flush([existing])
                return existing
            raise

        db.session.flush()
        selection = PickerSelection.query.filter_by(
            session_id=ps.id, google_media_id=item_id
        ).first()
        if selection and is_duplicate and selection.status != "dup":
            selection.status = "dup"
            selection.updated_at = now
            db.session.flush([selection])
        return selection

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
        # ps.status = "imported"  # 削除: 新しいアイテムをキューに追加しただけで、まだインポート完了ではない
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
        if ps.status in ("importing", "imported", "canceled", "expired", "error"):
            return {"error": "already_done"}, 409

        existing = (
            JobSync.query
            .filter(
                JobSync.target == "picker_import",
                JobSync.session_id == ps.id,
                JobSync.status.in_(("queued", "running")),
            )
            .order_by(JobSync.started_at.is_(None), JobSync.started_at.desc())
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
            if job.celery_task:
                job.celery_task.status = CeleryTaskStatus.FAILED
                job.celery_task.finished_at = job.finished_at
                job.celery_task.error_message = str(e)
            ps.status = "error"
            ps.last_progress_at = datetime.now(timezone.utc)
            db.session.commit()
            return {"error": "enqueue_failed"}, 500

        return {"enqueued": True, "jobId": job.id, "celeryTaskId": task_id, "status": "queued"}, 202

    @staticmethod
    def _create_job(ps: PickerSession, account_id: int) -> Tuple[JobSync, str]:
        task_id = uuid4().hex
        task_record = CeleryTaskRecord(
            task_name="job_sync.picker_import",
            object_type="picker_session",
            object_id=str(ps.id),
            status=CeleryTaskStatus.QUEUED,
        )
        db.session.add(task_record)

        job = JobSync(
            target="picker_import",
            task_name="picker_import.watchdog",
            trigger="worker",
            account_id=account_id,
            session_id=ps.id,
            celery_task=task_record,
            started_at=None,
            finished_at=None,
            stats_json=json.dumps({"celery_task_id": task_id, "selected": getattr(ps, "selected_count", 0)}),
        )
        db.session.add(job)
        stats = ps.stats()
        stats["celery_task_id"] = task_id
        stats["job_id"] = None
        ps.set_stats(stats)
        ps.status = "importing"  # 修正: enqueued → importing
        ps.last_progress_at = datetime.now(timezone.utc)
        db.session.flush()
        stats["job_id"] = job.id
        ps.set_stats(stats)
        task_record.update_payload({"job_id": job.id, "celery_task_id": task_id})
        db.session.commit()
        return job, task_id

    @staticmethod
    def _publish_celery(ps: PickerSession, job: JobSync, task_id: str) -> None:
        """Publish Celery task for picker import session."""
        try:
            # Try to import and use Celery watchdog task
            from cli.src.celery.tasks import picker_import_watchdog_task
            
            # Start the watchdog task which will process all pending selections
            picker_import_watchdog_task.delay()
                
        except ImportError:
            # Fall back to dummy for tests or when Celery is not available
            print(f"Celery not available, would start watchdog for session {ps.id}")
        except Exception as e:
            current_app.logger.error(f"Failed to publish Celery task: {e}")
            if current_app.config.get("TESTING"):
                current_app.logger.warning(
                    "Celery publish failed in test mode; continuing without enqueue."
                )
                return
            raise

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
            .order_by(JobSync.started_at.is_(None), JobSync.started_at.desc())
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
            if job.celery_task:
                if job.status == "success":
                    job.celery_task.status = CeleryTaskStatus.SUCCESS
                elif job.status in ("failed", "error"):
                    job.celery_task.status = CeleryTaskStatus.FAILED
                else:
                    job.celery_task.status = CeleryTaskStatus.SUCCESS
                job.celery_task.finished_at = now
                job.celery_task.error_message = None
                job.celery_task.set_result({"countsByStatus": counts, "status": job.status})

        db.session.commit()
        return {"status": status, "countsByStatus": counts}, 200
