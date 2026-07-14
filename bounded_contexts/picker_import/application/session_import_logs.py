"""ピッカーセッションの取り込みログ収集。

セッション詳細画面のログ一覧は ``WorkerLog`` の ``local_import.%`` /
``import.%`` イベントを、セッション識別子（session_id・DB ID・アカウント
エイリアス）で照合して構築する。Flask 版 ``presentation/web/api/
picker_session.py`` にあったロジックを FastAPI 移行に伴い Application 層へ
移設したもの。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_

from shared.infrastructure.models.worker_log import WorkerLog
from shared.kernel.logging.logging_config import setup_task_logging

_LOG_SESSION_KEYS = {
    "session_id",
    "sessionId",
    "session_identifier",
    "sessionIdentifier",
    "session_key",
    "sessionKey",
    "session_db_id",
    "active_session_id",
    "target_session_id",
    "import_session_id",
    "importSessionId",
    "picker_session_id",
    "pickerSessionId",
}

_LOG_NESTED_SESSION_KEYS = {"session_id", "sessionId", "session_key", "sessionKey", "id"}

_import_request_logger: Optional[logging.Logger] = None


def _get_import_request_logger() -> logging.Logger:
    """取り込みリクエスト中のサーバーエラーを WorkerLog に残すロガー。

    セッション詳細画面のログは ``WorkerLog`` の ``import.%`` イベントを
    ``session_id`` で照合して表示するため、API 側の 500 もここ経由で記録する。
    """
    global _import_request_logger
    if _import_request_logger is None:
        _import_request_logger = setup_task_logging("picker_import")
    return _import_request_logger


def log_import_request_error(
    *,
    session_identifier: Optional[str],
    session_db_id: Optional[int],
    event: str,
    message: str,
    exc: Optional[BaseException] = None,
    **details: Any,
) -> None:
    """Persist an import-request server error to the session's worker log."""

    payload: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "message": message,
    }
    if session_identifier is not None:
        payload["session_id"] = session_identifier
    if session_db_id is not None:
        payload["session_db_id"] = session_db_id
    if exc is not None:
        payload["error_type"] = type(exc).__name__
        payload["error_message"] = str(exc)
    payload.update(details)

    _get_import_request_logger().error(
        json.dumps(payload, ensure_ascii=False, default=str),
        exc_info=exc if exc is not None else False,
        extra={"event": event},
    )


def _normalize_log_identifier(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    if isinstance(value, (int,)):
        return str(value)
    return None


def _extract_session_identifier_candidates(mapping: Any) -> set[str]:
    candidates: set[str] = set()
    if not isinstance(mapping, dict):
        return candidates

    for key in _LOG_SESSION_KEYS:
        if key in mapping:
            normalized = _normalize_log_identifier(mapping.get(key))
            if normalized:
                candidates.add(normalized)

    session_block = mapping.get("session")
    if isinstance(session_block, dict):
        for key in _LOG_NESTED_SESSION_KEYS:
            normalized = _normalize_log_identifier(session_block.get(key))
            if normalized:
                candidates.add(normalized)

    result_block = mapping.get("result")
    if isinstance(result_block, dict):
        candidates.update(_extract_session_identifier_candidates(result_block))

    details_block = mapping.get("details")
    if isinstance(details_block, dict):
        candidates.update(_extract_session_identifier_candidates(details_block))

    return candidates


def build_session_aliases(ps) -> set[str]:
    """ログ照合に使うセッション識別子のエイリアス集合を返す。"""
    session_aliases: set[str] = set()
    if not ps:
        return session_aliases

    session_identifier = getattr(ps, "session_id", None)

    def _add_alias(value: Any) -> None:
        normalized = _normalize_log_identifier(value)
        if normalized:
            session_aliases.add(normalized)

    _add_alias(session_identifier)

    if session_identifier:
        base_identifier = session_identifier.split("#", 1)[0]
        _add_alias(base_identifier)
        if "/" in base_identifier:
            _add_alias(base_identifier.split("/", 1)[-1])

    account_id = getattr(ps, "account_id", None)
    if account_id is not None:
        _add_alias(f"google-{account_id}")

    db_id = getattr(ps, "id", None)
    if db_id is not None:
        _add_alias(db_id)

    return session_aliases


def collect_local_import_logs(
    ps,
    limit=None,
    include_raw: bool = False,
    file_task_id: Optional[str] = None,
    file_task_id_index: Optional[Dict[str, int]] = None,
    *,
    before_log_id: Optional[int] = None,
    after_log_id: Optional[int] = None,
    return_meta: bool = False,
):
    """Collect import logs for a picker session.

    Args:
        ps: Picker session model instance.
        limit: Optional number of log entries to return. ``None`` returns all
            matching entries.
        include_raw: When ``True`` the original log payloads and metadata are
            included in the response dictionaries.
        file_task_id: Optional identifier to scope logs to a single processed file.
        file_task_id_index: Optional mapping updated with the first log ID for
            each encountered ``file_task_id``.

    Returns:
        List of log dictionaries sorted by ID ascending. When ``return_meta``
        is ``True`` a ``(logs, meta)`` tuple is returned instead.
    """

    if not ps:
        return ([], {}) if return_meta else []

    session_aliases = build_session_aliases(ps)
    account_identifier = None
    if getattr(ps, "account_id", None) is not None:
        account_identifier = _normalize_log_identifier(ps.account_id)

    query = WorkerLog.query.filter(
        or_(WorkerLog.event.like("local_import%"), WorkerLog.event.like("import.%"))
    )

    def _apply_session_scope(worker_query):
        if not session_aliases:
            return worker_query

        normalized_aliases = [alias for alias in session_aliases if alias]

        if not normalized_aliases:
            return worker_query

        # 最も一般的に使用されるJSONパスのみに絞る
        json_paths = [
            "$.session_id",
            "$.sessionId",
            "$.import_session_id",
            "$.picker_session_id",
        ]

        filters = []
        for alias in normalized_aliases:
            # メッセージ内の文字列検索
            filters.append(WorkerLog.message.contains(alias))

            # 数値IDかどうかチェック
            alias_numeric: Optional[int] = None
            try:
                alias_numeric = int(alias)
            except (TypeError, ValueError):
                pass

            # JSONフィールド検索 - 効率化のため条件を絞る
            for column in (WorkerLog.extra_json, WorkerLog.meta_json):
                for path in json_paths:
                    json_expr = func.json_extract(column, path)
                    if alias_numeric is not None:
                        # 数値IDの場合は数値比較のみ
                        filters.append(json_expr == alias_numeric)
                    else:
                        # 文字列IDの場合はJSON引用形式での比較
                        filters.append(json_expr == func.json_quote(alias))

        if filters:
            worker_query = worker_query.filter(or_(*filters))

        return worker_query

    before_id: Optional[int] = None
    if before_log_id is not None:
        try:
            before_id = int(before_log_id)
        except (TypeError, ValueError):
            before_id = None

    after_id: Optional[int] = None
    if after_log_id is not None:
        try:
            after_id = int(after_log_id)
        except (TypeError, ValueError):
            after_id = None

    query = _apply_session_scope(query)

    if file_task_id:
        query = query.filter(WorkerLog.file_task_id == file_task_id)

    if after_id is not None:
        query = query.filter(WorkerLog.id > after_id)

    if before_id is not None:
        query = query.filter(WorkerLog.id < before_id)

    bounded_limit: Optional[int] = None

    if limit is None:
        # limit未指定の場合は最大件数を設定して暴走を防ぐ
        query = query.order_by(WorkerLog.id.asc()).limit(10000)
    else:
        # scan_multiplierを小さくして負荷を軽減
        scan_multiplier = 3 if file_task_id_index is None else 5
        bounded_limit = max(limit * scan_multiplier, limit, 100)
        # 最大5000件に制限
        bounded_limit = min(bounded_limit, 5000)
        query = query.order_by(WorkerLog.id.desc()).limit(bounded_limit)

    def _transform_row(row):
        try:
            payload = json.loads(row.message)
        except Exception:
            payload = {"message": row.message}

        if not isinstance(payload, dict):
            payload = {"message": payload}

        extras: Dict[str, Any] = {}
        payload_extras = payload.get("_extra")
        if isinstance(payload_extras, dict):
            extras.update(payload_extras)

        row_extras = row.extra_json if isinstance(row.extra_json, dict) else None
        if row_extras:
            extras.update(row_extras)

        def _coerce_progress_step(value: Any) -> Optional[int]:
            if value is None:
                return None
            if isinstance(value, bool):
                return None
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                candidate = value.strip()
                if not candidate:
                    return None
                try:
                    return int(candidate)
                except ValueError:
                    return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        progress_step = row.progress_step
        if progress_step is None:
            for candidate in (
                extras.get("progress_step"),
                extras.get("progressStep"),
                payload.get("progress_step"),
                payload.get("progressStep"),
            ):
                progress_step = _coerce_progress_step(candidate)
                if progress_step is not None:
                    break

        candidate_values = set()
        candidate_values.update(_extract_session_identifier_candidates(extras))
        candidate_values.update(_extract_session_identifier_candidates(payload))

        session_matches = bool(session_aliases.intersection(candidate_values))

        if not session_matches and account_identifier is not None:
            for container in (extras, payload):
                if not isinstance(container, dict):
                    continue
                account_value = _normalize_log_identifier(
                    container.get("account_id") or container.get("accountId")
                )
                if account_value != account_identifier:
                    continue

                source_value = container.get("import_source") or container.get("source")
                if isinstance(source_value, str) and source_value.lower().startswith("google"):
                    session_matches = True
                    break

        if not session_matches:
            return None

        excluded_keys = {
            "session_id",
            "session_db_id",
            "active_session_id",
            "target_session_id",
            "status",
            "progress_step",
            "progressStep",
        }

        details = {
            key: value
            for key, value in extras.items()
            if key not in excluded_keys
        }

        status_value = row.status or payload.get("status") or extras.get("status")

        if status_value is not None and not isinstance(status_value, str):
            try:
                status_value = str(status_value)
            except Exception:
                status_value = None

        message = payload.get("message")
        if not isinstance(message, str):
            try:
                message = json.dumps(message, ensure_ascii=False, default=str)
            except Exception:
                message = str(message)

        log_entry = {
            "id": row.id,
            "createdAt": row.created_at.isoformat().replace("+00:00", "Z")
            if row.created_at
            else None,
            "level": row.level,
            "event": row.event,
            "status": status_value,
            "message": message,
            "details": details,
        }

        if row.file_task_id:
            log_entry["fileTaskId"] = row.file_task_id

        if progress_step is not None:
            log_entry["progressStep"] = progress_step

        if include_raw:
            log_entry["raw"] = {
                "id": row.id,
                "created_at": row.created_at.isoformat().replace("+00:00", "Z")
                if row.created_at
                else None,
                "level": row.level,
                "event": row.event,
                "status": row.status,
                "logger_name": row.logger_name,
                "task_name": row.task_name,
                "task_uuid": row.task_uuid,
                "worker_hostname": row.worker_hostname,
                "queue_name": row.queue_name,
                "file_task_id": row.file_task_id,
                "progress_step": row.progress_step
                if row.progress_step is not None
                else progress_step,
                "raw_message": row.message,
                "parsed_message": payload,
                "extra_json": row.extra_json,
                "meta_json": row.meta_json,
                "trace": row.trace,
            }

        return log_entry

    logs: List[Dict[str, Any]] = []
    tracked_file_task_ids: set[str] = set()
    extracted_present = False

    for row in query:
        log_entry = _transform_row(row)
        if log_entry is None:
            continue

        if file_task_id_index is not None and row.file_task_id:
            current_index = file_task_id_index.get(row.file_task_id)
            if current_index is None or row.id < current_index:
                file_task_id_index[row.file_task_id] = row.id

        file_task_id_value = log_entry.get("fileTaskId")
        if isinstance(file_task_id_value, str):
            tracked_file_task_ids.add(file_task_id_value)

        if limit is not None and len(logs) >= limit:
            if file_task_id_index is None:
                break
            if tracked_file_task_ids and tracked_file_task_ids.issubset(
                file_task_id_index.keys()
            ):
                break
            continue

        logs.append(log_entry)
        if log_entry.get("event") == "local_import.zip.extracted":
            extracted_present = True

    oldest_id: Optional[int] = None
    newest_id: Optional[int] = None

    if logs:
        id_values = [entry.get("id") for entry in logs if isinstance(entry.get("id"), int)]
        if id_values:
            oldest_id = min(id_values)
            newest_id = max(id_values)

    if limit is not None:
        logs.sort(key=lambda item: item.get("id", 0))

        if not extracted_present:
            fallback_query = WorkerLog.query.filter(
                WorkerLog.event == "local_import.zip.extracted"
            )
            fallback_query = _apply_session_scope(fallback_query)
            if file_task_id:
                fallback_query = fallback_query.filter(WorkerLog.file_task_id == file_task_id)
            if after_id is not None:
                fallback_query = fallback_query.filter(WorkerLog.id > after_id)
            if before_id is not None:
                fallback_query = fallback_query.filter(WorkerLog.id < before_id)
            fallback_query = fallback_query.order_by(WorkerLog.id.asc())
            if bounded_limit is not None:
                fallback_query = fallback_query.limit(bounded_limit)

            fallback_entry = None
            for row in fallback_query:
                entry = _transform_row(row)
                if entry is None:
                    continue
                if file_task_id_index is not None and row.file_task_id:
                    existing_index = file_task_id_index.get(row.file_task_id)
                    if existing_index is None or row.id < existing_index:
                        file_task_id_index[row.file_task_id] = row.id
                fallback_entry = entry

            if fallback_entry and fallback_entry.get("id") not in {
                item.get("id") for item in logs
            }:
                logs.append(fallback_entry)
                logs.sort(key=lambda item: item.get("id", 0))
                if len(logs) > limit:
                    if limit == 1:
                        logs = [fallback_entry]
                    else:
                        trimmed = [
                            item
                            for item in logs
                            if item.get("id") != fallback_entry.get("id")
                        ]
                        trimmed = trimmed[-(limit - 1):]
                        trimmed.append(fallback_entry)
                        trimmed.sort(key=lambda item: item.get("id", 0))
                        logs = trimmed

    if logs:
        id_values = [entry.get("id") for entry in logs if isinstance(entry.get("id"), int)]
        if id_values:
            oldest_id = min(id_values)
            newest_id = max(id_values)

    has_more = False
    if (
        return_meta
        and limit is not None
        and after_id is None
        and oldest_id is not None
    ):
        more_query = WorkerLog.query
        more_query = _apply_session_scope(more_query)
        if file_task_id:
            more_query = more_query.filter(WorkerLog.file_task_id == file_task_id)
        more_query = more_query.filter(WorkerLog.id < oldest_id)
        more_query = more_query.order_by(WorkerLog.id.asc()).limit(1)
        has_more = more_query.first() is not None

    next_cursor = oldest_id if has_more else None

    if return_meta:
        meta = {
            "has_more": has_more,
            "next_cursor": next_cursor,
            "oldest_log_id": oldest_id,
            "newest_log_id": newest_id,
        }
        return logs, meta

    return logs
