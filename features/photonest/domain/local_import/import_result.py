"""ローカルインポート結果の値オブジェクト."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Mapping


@dataclass
class ImportTaskResult:
    """ローカルインポート処理全体の集計結果を保持する不変に近い値オブジェクト."""

    ok: bool = True
    processed: int = 0
    success: int = 0
    skipped: int = 0
    failed: int = 0
    canceled: bool = False
    session_id: Optional[str] = None
    celery_task_id: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    details: List[Dict[str, Any]] = field(default_factory=list)
    thumbnail_records: List[Dict[str, Any]] = field(default_factory=list)
    duplicates: int = 0
    manually_skipped: int = 0
    failure_reasons: List[str] = field(default_factory=list)
    thumbnail_snapshot: Optional[Dict[str, Any]] = None
    _metadata: Dict[str, Any] = field(default_factory=dict, repr=False)

    def mark_failed(self) -> None:
        """エラー発生により ``ok`` フラグを下げる."""

        self.ok = False

    def add_error(self, message: Any, *, mark_failed: bool = True) -> None:
        """エラーを追加し必要に応じて ``ok`` を ``False`` にする."""

        if mark_failed:
            self.mark_failed()
        if message:
            self.errors.append(str(message))

    def append_detail(self, detail: Dict[str, Any]) -> None:
        """詳細情報を追加する."""

        if detail:
            self.details.append(detail)

    def increment_processed(self, *, amount: int = 1) -> None:
        self.processed += amount

    def increment_success(self, *, amount: int = 1) -> None:
        self.success += amount

    def increment_skipped(self, *, amount: int = 1) -> None:
        self.skipped += amount

    def increment_failed(self, *, amount: int = 1, mark_failed: bool = True) -> None:
        self.failed += amount
        if mark_failed:
            self.mark_failed()

    def mark_canceled(self) -> None:
        self.canceled = True

    def set_session_id(self, session_id: Optional[str]) -> None:
        self.session_id = session_id

    def set_celery_task_id(self, celery_task_id: Optional[str]) -> None:
        self.celery_task_id = celery_task_id

    def add_thumbnail_record(self, record: Dict[str, Any]) -> None:
        if record:
            self.thumbnail_records.append(record)

    def set_thumbnail_snapshot(self, snapshot: Optional[Dict[str, Any]]) -> None:
        self.thumbnail_snapshot = snapshot

    def set_duplicates(self, *, duplicates: int, manually_skipped: int) -> None:
        self.duplicates = duplicates
        self.manually_skipped = manually_skipped

    def set_failure_reasons(self, reasons: Iterable[str]) -> None:
        self.failure_reasons = [str(reason) for reason in reasons if reason]

    def metadata(self) -> Dict[str, Any]:
        return self._metadata

    def set_metadata(self, key: str, value: Any) -> None:
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        return self._metadata.get(key, default)

    def collect_failure_reasons(self) -> List[str]:
        """エラー詳細からユニークな失敗理由を抽出する."""

        reasons: List[str] = []
        seen: set[str] = set()

        for entry in self.errors:
            if not entry:
                continue
            text = str(entry)
            if text not in seen:
                reasons.append(text)
                seen.add(text)

        for detail in self.details:
            if not isinstance(detail, dict):
                continue
            if detail.get("status") != "failed":
                continue
            detail_reason = detail.get("reason") or "理由不明"
            if detail.get("file"):
                detail_reason = f"{detail['file']}: {detail_reason}"
            if detail_reason not in seen:
                reasons.append(detail_reason)
                seen.add(detail_reason)

        return reasons

    def to_dict(self) -> Dict[str, Any]:
        """API やテストで利用する辞書形式へ変換する."""

        payload: Dict[str, Any] = {
            "ok": self.ok,
            "errors": list(self.errors),
            "processed": self.processed,
            "success": self.success,
            "skipped": self.skipped,
            "failed": self.failed,
            "details": [dict(detail) for detail in self.details],
            "session_id": self.session_id,
            "celery_task_id": self.celery_task_id,
            "canceled": self.canceled,
        }

        if self.thumbnail_records:
            payload["thumbnail_records"] = [dict(entry) for entry in self.thumbnail_records]
        if self.thumbnail_snapshot is not None:
            payload["thumbnail_snapshot"] = self.thumbnail_snapshot
        if self.failure_reasons:
            payload["failure_reasons"] = list(self.failure_reasons)
        if self.duplicates:
            payload["duplicates"] = self.duplicates
        if self.manually_skipped:
            payload["manually_skipped"] = self.manually_skipped

        if self._metadata:
            payload.update(self._metadata)

        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ImportTaskResult":
        """Create an :class:`ImportTaskResult` from a legacy dictionary payload."""

        result = cls(
            ok=bool(data.get("ok", True)),
            processed=int(data.get("processed", 0)),
            success=int(data.get("success", 0)),
            skipped=int(data.get("skipped", 0)),
            failed=int(data.get("failed", 0)),
            canceled=bool(data.get("canceled", False)),
            session_id=data.get("session_id"),
            celery_task_id=data.get("celery_task_id"),
        )

        result.errors.extend(str(entry) for entry in data.get("errors", []))
        result.details.extend(list(data.get("details", [])))
        result.thumbnail_records.extend(list(data.get("thumbnail_records", [])))

        snapshot = data.get("thumbnail_snapshot")
        if snapshot is not None:
            result.thumbnail_snapshot = snapshot

        result.duplicates = int(data.get("duplicates", 0))
        result.manually_skipped = int(data.get("manually_skipped", 0))

        failure_reasons = data.get("failure_reasons")
        if failure_reasons:
            result.failure_reasons = [str(reason) for reason in failure_reasons]

        metadata_keys = set(data.keys()) - {
            "ok",
            "processed",
            "success",
            "skipped",
            "failed",
            "canceled",
            "session_id",
            "celery_task_id",
            "errors",
            "details",
            "thumbnail_records",
            "thumbnail_snapshot",
            "failure_reasons",
            "duplicates",
            "manually_skipped",
        }
        for key in metadata_keys:
            result.set_metadata(key, data[key])

        return result


__all__ = ["ImportTaskResult"]
