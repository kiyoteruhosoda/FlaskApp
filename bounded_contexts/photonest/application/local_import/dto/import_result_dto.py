"""データ転送オブジェクト（DTO）."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ImportResultDTO:
    """インポート処理の結果を表すDTO."""
    
    ok: bool = True
    session_id: Optional[str] = None
    celery_task_id: Optional[str] = None
    
    # カウント情報
    total_files: int = 0
    imported_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    
    # エラー情報
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    
    # 詳細情報
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換."""
        result = {
            "ok": self.ok,
            "total": self.total_files,
            "imported": self.imported_count,
            "duplicates": self.duplicate_count,
            "errors": self.error_count,
            "skipped": self.skipped_count,
        }
        
        if self.session_id:
            result["session_id"] = self.session_id
        
        if self.celery_task_id:
            result["celery_task_id"] = self.celery_task_id
        
        if not self.ok and self.error_message:
            result["error"] = self.error_message
            if self.error_type:
                result["error_type"] = self.error_type
        
        if self.details:
            result.update(self.details)
        
        return result
    
    def add_imported(self) -> None:
        """インポート成功をカウント."""
        self.imported_count += 1
        self.total_files += 1
    
    def add_duplicate(self) -> None:
        """重複をカウント."""
        self.duplicate_count += 1
        self.total_files += 1
    
    def add_error(self) -> None:
        """エラーをカウント."""
        self.error_count += 1
        self.total_files += 1
    
    def add_skipped(self) -> None:
        """スキップをカウント."""
        self.skipped_count += 1
        self.total_files += 1
    
    def mark_failed(self, error: str, error_type: Optional[str] = None) -> None:
        """処理全体を失敗としてマーク."""
        self.ok = False
        self.error_message = error
        self.error_type = error_type


@dataclass
class FileImportDTO:
    """単一ファイルのインポート結果を表すDTO."""
    
    ok: bool
    status: str  # imported / dup / error / skipped
    media_id: Optional[int] = None
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換."""
        result = {
            "ok": self.ok,
            "status": self.status,
        }
        
        if self.media_id:
            result["media_id"] = self.media_id
        
        if self.file_path:
            result["file_path"] = self.file_path
        
        if self.error_message:
            result["error"] = self.error_message
        
        return result
