"""インポート状態を表す値オブジェクト."""
from __future__ import annotations
from enum import Enum


class ImportStatus(str, Enum):
    """インポート状態.
    
    PickerSelectionのstatusフィールドに対応。
    """
    
    ENQUEUED = "enqueued"  # キューに追加済み
    IMPORTING = "importing"  # 処理中
    IMPORTED = "imported"  # 正常完了
    DUPLICATE = "dup"  # 重複として処理完了
    ERROR = "error"  # エラー
    CANCELLED = "cancelled"  # キャンセル
    
    @classmethod
    def from_string(cls, value: str) -> ImportStatus:
        """文字列からImportStatusを生成."""
        try:
            return cls(value)
        except ValueError:
            raise ValueError(f"Invalid import status: {value}")
    
    def is_terminal(self) -> bool:
        """終端状態かどうか（再処理不要）."""
        return self in {
            self.IMPORTED,
            self.DUPLICATE,
            self.CANCELLED,
        }
    
    def is_successful(self) -> bool:
        """成功状態かどうか."""
        return self in {
            self.IMPORTED,
            self.DUPLICATE,
        }
    
    def is_error(self) -> bool:
        """エラー状態かどうか."""
        return self == self.ERROR
