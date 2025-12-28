"""インポートポリシー."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .commands import ImportCommand


@dataclass(slots=True)
class ImportPolicy:
    """インポート処理の事前検証を担うポリシー."""

    def enforce(self, command: ImportCommand) -> None:
        if command.source == "local":
            if not command.directory_path:
                raise ValueError("ローカルインポートには directory_path が必要です")
            if not Path(command.directory_path).exists():
                raise FileNotFoundError(
                    f"取り込み対象ディレクトリが存在しません: {command.directory_path}"
                )
        elif command.source == "google":
            if not command.account_id:
                raise ValueError("Google インポートには account_id が必要です")
        else:
            raise ValueError(f"未サポートのインポートソースです: {command.source}")


__all__ = ["ImportPolicy"]
