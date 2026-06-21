"""ローカルインポートのファイル単位イベントを DB 監査ログへ記録するアダプタ.

アプリケーション層(:class:`LocalImportQueueProcessor`)から注入される
``audit_recorder`` の実体。1ファイル=1エントリで取り込み状態・エラー原因を
``local_import_audit_log`` テーブルへ残し、Web UI / 状態 API から
``/items/<item_id>/logs`` や ``/sessions/<id>/logs`` で追跡できるようにする。

- 監査ロガー(グローバル)が未初期化なら黙ってスキップ(本体に影響させない)。
- 失敗ファイルは ``level=error`` / ``category=error`` で記録し、
  ``error_type`` / ``error_message`` を埋めてエラー一覧 API に載るようにする。
- 成功・重複は ``file_operation`` カテゴリで ``from_state`` → ``to_state`` を残す。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from bounded_contexts.photonest.infrastructure.local_import.audit_logger import (
    AuditLogEntry,
    LogCategory,
    LogLevel,
)
from bounded_contexts.photonest.infrastructure.local_import.logging_integration import (
    get_audit_logger,
)

logger = logging.getLogger(__name__)


def _status_label(status: Optional[str]) -> str:
    return {
        "imported": "取り込み成功",
        "dup": "重複(スキップ)",
        "failed": "取り込み失敗",
        "skipped": "スキップ",
    }.get(status or "", status or "不明")


def _build_item_entry(record: Dict[str, Any]) -> AuditLogEntry:
    status = record.get("status")
    failed = bool(record.get("failed")) or status == "failed"
    filename = record.get("file") or record.get("filename") or record.get("item_id")
    reason = record.get("reason")

    details: Dict[str, Any] = {
        "file_path": record.get("file_path"),
        "filename": record.get("filename"),
        "status": status,
        "attempts": record.get("attempts"),
        "media_id": record.get("media_id"),
        "reason": reason,
        "celery_task_id": record.get("celery_task_id"),
    }
    thumbnail = record.get("thumbnail")
    if thumbnail is not None:
        details["thumbnail"] = thumbnail
    # None を取り除いて見やすくする。
    details = {k: v for k, v in details.items() if v is not None}

    message = f"{filename}: {_status_label(status)}"
    if failed and reason:
        message = f"{message} - {reason}"

    entry = AuditLogEntry(
        level=LogLevel.ERROR if failed else LogLevel.INFO,
        category=LogCategory.ERROR if failed else LogCategory.FILE_OPERATION,
        message=message,
        session_id=record.get("session_id"),
        item_id=record.get("item_id"),
        task_id=record.get("celery_task_id"),
        details=details,
        error_type=record.get("error_type") if failed else None,
        error_message=reason if failed else None,
    )
    # from_audit_entry が getattr で拾うため、属性として付与する。
    entry.from_state = record.get("from_state")
    entry.to_state = record.get("to_state") or status
    return entry


def _build_resume_entry(record: Dict[str, Any]) -> AuditLogEntry:
    details = {
        k: v
        for k, v in record.items()
        if k not in {"kind", "session_id"} and v is not None
    }
    message = (
        "取り込みを再開: "
        f"完了={record.get('done', 0)} "
        f"残り={record.get('pending', 0)} "
        f"中断={record.get('interrupted', 0)} "
        f"失敗={record.get('failed', 0)}"
    )
    return AuditLogEntry(
        level=LogLevel.INFO,
        category=LogCategory.STATE_TRANSITION,
        message=message,
        session_id=record.get("session_id"),
        details=details,
    )


def record_local_import_event(record: Dict[str, Any]) -> None:
    """キュー処理から渡されたレコードを DB 監査ログへ書き込む.

    監査ロガーが利用不可・記録失敗時も例外を投げず黙って戻る。
    """

    audit_logger = get_audit_logger()
    if audit_logger is None:
        return

    try:
        kind = record.get("kind")
        if kind == "resume_summary":
            entry = _build_resume_entry(record)
        else:
            entry = _build_item_entry(record)
        audit_logger.log(entry)
    except Exception as exc:  # pragma: no cover - 監査ログ失敗は本体に影響させない
        logger.warning("ファイル単位の監査ログ記録に失敗: %s", exc)
