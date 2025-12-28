"""ファイル移動の実装."""
from __future__ import annotations
import os
import shutil
from pathlib import Path
from typing import Protocol


class Logger(Protocol):
    """ロガーのプロトコル."""
    
    def warning(self, message: str, **details) -> None:
        ...
    
    def error(self, message: str, **details) -> None:
        ...


class FileMover:
    """ファイル移動の実装.
    
    責務：
    - ファイルのアトミックな移動
    - ディレクトリの自動作成
    - エラー時のフォールバック（コピー＋削除）
    """
    
    def __init__(self, logger: Logger) -> None:
        self._logger = logger
    
    def move(self, source: str, destination: str) -> bool:
        """ファイルを移動.
        
        Args:
            source: ソースファイルパス
            destination: 移動先ファイルパス
            
        Returns:
            成功時True、失敗時False
        """
        try:
            # 移動先ディレクトリを作成
            dest_path = Path(destination)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # アトミックな移動を試行
            try:
                shutil.move(str(source), str(destination))
                return True
            except OSError:
                # 失敗した場合はコピー＋削除
                shutil.copy2(str(source), str(destination))
                try:
                    os.remove(str(source))
                except OSError as remove_err:
                    self._logger.warning(
                        f"Failed to remove source after copy: {source}",
                        error=str(remove_err),
                    )
                return True
                
        except Exception as exc:
            self._logger.error(
                f"Failed to move file: {source} -> {destination}",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return False
    
    def copy(self, source: str, destination: str) -> bool:
        """ファイルをコピー.
        
        Args:
            source: ソースファイルパス
            destination: コピー先ファイルパス
            
        Returns:
            成功時True、失敗時False
        """
        try:
            dest_path = Path(destination)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(destination))
            return True
        except Exception as exc:
            self._logger.error(
                f"Failed to copy file: {source} -> {destination}",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return False
    
    def delete(self, file_path: str) -> bool:
        """ファイルを削除.
        
        Args:
            file_path: 削除対象ファイルパス
            
        Returns:
            成功時True、失敗時False
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            return True
        except Exception as exc:
            self._logger.error(
                f"Failed to delete file: {file_path}",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return False
    
    def exists(self, file_path: str) -> bool:
        """ファイルが存在するか確認."""
        return os.path.exists(file_path)
