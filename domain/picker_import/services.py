from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Protocol

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


class PerceptualHashCalculator(Protocol):
    """知覚ハッシュ計算を抽象化するためのポート。"""

    def calculate(
        self,
        *,
        file_path: Path,
        is_video: bool,
        duration_ms: Optional[int],
    ) -> Optional[str]:
        ...


@dataclass
class MediaHashingService:
    """メディア取り込み時に知覚ハッシュを生成するドメインサービス。"""

    calculator: PerceptualHashCalculator

    def compute(
        self,
        *,
        file_path: Path,
        is_video: bool,
        duration_ms: Optional[int],
    ) -> Optional[str]:
        """知覚ハッシュを計算して返す。"""

        return self.calculator.calculate(
            file_path=file_path,
            is_video=is_video,
            duration_ms=duration_ms,
        )
