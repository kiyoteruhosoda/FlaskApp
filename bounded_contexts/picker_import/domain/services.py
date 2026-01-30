"""Picker Import domain services.

インポート処理に関するドメインサービスを定義します。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol, runtime_checkable

from .entities import ImportSelection, ImportSessionProgress


@dataclass(slots=True)
class ImportResultAggregator:
    """Selection処理結果を集計するドメインサービス。"""

    progress: ImportSessionProgress

    def register_success(self, *, duplicated: bool) -> None:
        """成功を記録（重複フラグ付き）."""
        if duplicated:
            self.progress.duplicated += 1
        else:
            self.progress.imported += 1

    def register_failure(self) -> None:
        """単一の失敗を記録."""
        self.progress.failed += 1

    def register_failures(self, count: int) -> None:
        """複数の失敗を記録."""
        self.progress.failed += max(0, count)


@dataclass(frozen=True, slots=True)
class SelectionClassifier:
    """Selectionの状態を判定するドメインサービス。"""

    def classify(self, selection: ImportSelection) -> str:
        """Selectionの現在状態を分類."""
        if selection.is_terminal():
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
        return "imported"
    if progress.failed:
        return "error"
    return "ready"


@runtime_checkable
class PerceptualHashCalculator(Protocol):
    """知覚ハッシュ計算を抽象化するためのポート。"""

    def calculate(
        self,
        *,
        file_path: Path,
        is_video: bool,
        duration_ms: int | None,
    ) -> str | None:
        """知覚ハッシュを計算して返す."""
        ...


@dataclass(frozen=True, slots=True)
class MediaHashingService:
    """メディア取り込み時に知覚ハッシュを生成するドメインサービス。"""

    calculator: PerceptualHashCalculator

    def compute(
        self,
        *,
        file_path: Path,
        is_video: bool,
        duration_ms: int | None,
    ) -> str | None:
        """知覚ハッシュを計算して返す。"""
        return self.calculator.calculate(
            file_path=file_path,
            is_video=is_video,
            duration_ms=duration_ms,
        )
