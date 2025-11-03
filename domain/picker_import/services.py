from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .entities import ImportSelection, ImportSessionProgress


@dataclass
class ImportResultAggregator:
    """Selection処理結果を集計するシンプルなサービス。"""

    progress: ImportSessionProgress

    def register_success(self, duplicated: bool) -> None:
        if duplicated:
            self.progress.duplicated += 1
        else:
            self.progress.imported += 1

    def register_failure(self) -> None:
        self.register_failures(1)

    def register_failures(self, count: int) -> None:
        self.progress.failed += max(0, count)


class SelectionClassifier:
    """Selectionの状態を判定する小さなドメインサービス。"""

    TERMINAL_STATES = {"imported", "dup", "failed", "expired"}

    def classify(self, selection: ImportSelection) -> str:
        if selection.status in self.TERMINAL_STATES:
            return "terminal"
        if selection.locked_by and selection.locked_at:
            return "running"
        return selection.status


def is_session_finished(selections: Iterable[ImportSelection]) -> bool:
    """すべてのSelectionが終端状態かを判定。"""

    return all(selection.is_terminal() for selection in selections)


def determine_session_status(progress: ImportSessionProgress) -> str:
    """セッションの状態を集計結果から決定。"""

    if progress.imported or progress.duplicated:
        if progress.failed:
            return "imported"
        return "imported"
    if progress.failed:
        return "error"
    return "ready"
