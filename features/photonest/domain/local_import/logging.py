"""ローカルインポート処理のための共通ロギングユーティリティ。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple


def serialize_details(details: Dict[str, Any]) -> str:
    """詳細情報をJSON文字列へ変換。失敗時は文字列表現を返す。"""

    if not details:
        return ""

    try:
        return json.dumps(details, ensure_ascii=False, default=str)
    except TypeError:
        return str(details)


def compose_message(
    message: str,
    details: Dict[str, Any],
    status: Optional[str] = None,
) -> str:
    """メッセージと詳細を結合してログに出力する文字列を生成。"""

    payload = details
    if status is not None:
        payload = dict(details)
        payload.setdefault("status", status)

    serialized = serialize_details(payload)
    if not serialized:
        return message
    return f"{message} | details={serialized}"


def with_session(details: Dict[str, Any], session_id: Optional[str]) -> Dict[str, Any]:
    """ログ詳細に session_id を追加した辞書を返す。"""

    merged = dict(details)
    if session_id is not None and "session_id" not in merged:
        merged["session_id"] = session_id
    return merged


def file_log_context(
    file_path: Optional[str],
    filename: Optional[str] = None,
    *,
    file_task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """ファイル関連ログに共通のコンテキストを生成する。"""

    context: Dict[str, Any] = {}
    base_name = filename

    if not base_name and file_path:
        base_name = file_path.split("/")[-1]

    display_value = file_path or base_name

    if display_value:
        context["file"] = display_value

    if file_path:
        context["file_path"] = file_path
        if base_name and base_name != file_path:
            context["basename"] = base_name
    elif base_name:
        context["basename"] = base_name

    if file_task_id:
        context["file_task_id"] = file_task_id

    return context


def existing_media_destination_context(media, originals_dir: Optional[str]) -> Dict[str, Any]:
    """既存メディアの保存先情報をログ用に組み立てる。"""

    details: Dict[str, Any] = {}

    if media is None:
        return details

    relative_path = getattr(media, "local_rel_path", None)
    if relative_path:
        details["relative_path"] = relative_path

        base_dir = originals_dir if originals_dir else None
        if base_dir:
            absolute_path = os.path.normpath(os.path.join(base_dir, relative_path))
        else:
            absolute_path = relative_path

        details["imported_path"] = absolute_path
        details["destination"] = absolute_path

    filename = getattr(media, "filename", None)
    if filename:
        details["imported_filename"] = filename

    return details


@dataclass(frozen=True)
class LogEntry:
    """ローカルインポートで扱うログ情報を表現する値オブジェクト。"""

    message: str
    details: Mapping[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    status: Optional[str] = None

    def compose(self, default_status: str) -> Tuple[str, Dict[str, Any], str]:
        """ログ出力に必要な情報を組み立てる。"""

        payload = with_session(dict(self.details), self.session_id)
        resolved_status = self.status if self.status is not None else default_status
        composed_message = compose_message(self.message, payload, resolved_status)
        return composed_message, payload, resolved_status


__all__ = [
    "compose_message",
    "existing_media_destination_context",
    "file_log_context",
    "LogEntry",
    "serialize_details",
    "with_session",
]

