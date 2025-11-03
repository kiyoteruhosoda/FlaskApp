from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional


@dataclass(frozen=True)
class ImportCommand:
    """ドメイン層で利用するインポート要求。"""

    picker_session_id: int
    account_id: int


@dataclass
class ImportSessionProgress:
    """セッション単位の進捗情報。"""

    imported: int = 0
    duplicated: int = 0
    failed: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "imported": self.imported,
            "dup": self.duplicated,
            "failed": self.failed,
        }


@dataclass
class ImportSelectionResult:
    """単一のSelectionを処理した結果。"""

    ok: bool
    status: str
    detail: Dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, object]:
        payload: Dict[str, object] = {"ok": self.ok, "status": self.status}
        if self.detail:
            payload.update(self.detail)
        return payload


@dataclass(frozen=True)
class ImportSelection:
    """選択されたメディア項目をドメインオブジェクトとして表現。"""

    selection_id: int
    session_id: int
    google_media_id: Optional[str]
    status: str
    attempts: int
    locked_by: Optional[str] = None
    locked_at: Optional[datetime] = None

    def is_terminal(self) -> bool:
        return self.status in {"imported", "dup", "failed", "expired"}


@dataclass
class ImportSession:
    """PickerSessionのドメイン表現。"""

    id: int
    account_id: Optional[int]
    status: str
    session_key: Optional[str]
    selected_count: int
    media_items_set: bool


@dataclass
class ImportResult:
    """セッション全体のインポート結果。"""

    ok: bool
    progress: ImportSessionProgress
    note: Optional[str] = None

    def to_payload(self) -> Dict[str, object]:
        payload: Dict[str, object] = {"ok": self.ok, **self.progress.to_dict()}
        if self.note is not None:
            payload["note"] = self.note
        return payload
