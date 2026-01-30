"""ローカルインポートで利用する値オブジェクトとエンティティ。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class ImportFile:
    """取り込み対象ファイルを表現する値オブジェクト。"""

    absolute_path: str

    @property
    def path(self) -> Path:
        return Path(self.absolute_path)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def extension(self) -> str:
        return self.path.suffix.lower()


@dataclass
class ImportOutcome:
    """ファイル取り込み結果を保持するドメインエンティティ。"""

    source: ImportFile
    status: str = "pending"
    details: Dict[str, Any] = field(default_factory=dict)

    def mark(self, status: str, **fields: Any) -> None:
        self.status = status
        if fields:
            self.details.update(fields)

    def as_dict(self) -> Dict[str, Any]:
        payload = dict(self.details)
        payload.setdefault("status", self.status)
        return payload


__all__ = ["ImportFile", "ImportOutcome"]

