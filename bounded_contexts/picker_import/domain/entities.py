"""Picker Import domain entities.

インポート処理に関するドメインエンティティと値オブジェクトを定義します。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Final


@dataclass(frozen=True, slots=True)
class ImportCommand:
    """ドメイン層で利用するインポート要求。"""

    picker_session_id: int
    account_id: int


@dataclass(slots=True)
class ImportSessionProgress:
    """セッション単位の進捗情報。"""

    imported: int = 0
    duplicated: int = 0
    failed: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "imported": self.imported,
            "dup": self.duplicated,
            "failed": self.failed,
        }


@dataclass(frozen=True, slots=True)
class ImportSelectionResult:
    """単一のSelectionを処理した結果。"""

    ok: bool
    status: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": self.ok, "status": self.status}
        if self.detail:
            payload.update(self.detail)
        return payload


@dataclass(frozen=True, slots=True)
class ImportSelection:
    """選択されたメディア項目をドメインオブジェクトとして表現。"""

    # 終端状態の定数
    TERMINAL_STATES: ClassVar[frozenset[str]] = frozenset(
        {"imported", "dup", "failed", "expired"}
    )

    selection_id: int
    session_id: int
    google_media_id: str | None
    status: str
    attempts: int
    locked_by: str | None = None
    locked_at: datetime | None = None

    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATES


@dataclass(slots=True)
class ImportSession:
    """PickerSessionのドメイン表現。"""

    id: int
    account_id: int | None
    status: str
    session_key: str | None
    selected_count: int
    media_items_set: bool


@dataclass(frozen=True, slots=True)
class ImportResult:
    """セッション全体のインポート結果。"""

    ok: bool
    progress: ImportSessionProgress
    note: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": self.ok, **self.progress.to_dict()}
        if self.note is not None:
            payload["note"] = self.note
        return payload
