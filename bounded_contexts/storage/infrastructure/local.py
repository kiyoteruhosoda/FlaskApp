"""Local filesystem storage実装."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import IO, Iterator

from ..domain import (
    StorageBackend,
    StorageConfiguration,
    StorageException,
    StorageMetadata,
    StorageNotFoundException,
    StoragePath,
    StoragePathResolverService,
    StoragePermissionException,
)

__all__ = ["LocalStorage"]


class LocalStorage:
    """ローカルファイルシステムのストレージバックエンド実装."""
    
    def __init__(self) -> None:
        self._configuration: StorageConfiguration | None = None
        self._path_resolver = StoragePathResolverService()
    
    def initialize(self, configuration: StorageConfiguration) -> None:
        """ローカルストレージを初期化."""
        self._configuration = configuration
        
        # ベースディレクトリを作成
        if configuration.base_path:
            base_dir = Path(configuration.base_path)
            try:
                base_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise StorageException(f"ベースディレクトリ作成エラー: {e}")
    
    def exists(self, path: StoragePath) -> bool:
        """ファイルが存在するかチェック."""
        file_path = self._resolve_file_path(path)
        return file_path.exists()
    
    def get_metadata(self, path: StoragePath) -> StorageMetadata:
        """ファイルメタデータを取得."""
        file_path = self._resolve_file_path(path)
        
        if not file_path.exists():
            raise StorageNotFoundException(f"ファイルが見つかりません: {path.relative_path}", path)
        
        try:
            stat = file_path.stat()
            import mimetypes
            content_type, _ = mimetypes.guess_type(str(file_path))
            
            return StorageMetadata(
                path=path,
                size=stat.st_size,
                content_type=content_type,
                etag=f'"{stat.st_mtime}-{stat.st_size}"',  # 簡易的なETag
                last_modified=stat.st_mtime,
                custom_metadata=None,
            )
        except OSError as e:
            raise StorageException(f"メタデータ取得エラー: {e}", path)
    
    def read(self, path: StoragePath) -> bytes:
        """ファイルの内容を読み込み."""
        file_path = self._resolve_file_path(path)
        
        if not file_path.exists():
            raise StorageNotFoundException(f"ファイルが見つかりません: {path.relative_path}", path)
        
        try:
            return file_path.read_bytes()
        except PermissionError:
            raise StoragePermissionException(f"読み込み権限エラー: {path.relative_path}", path)
        except OSError as e:
            raise StorageException(f"読み込みエラー: {e}", path)
    
    def read_stream(self, path: StoragePath) -> IO[bytes]:
        """ファイルをストリーミング読み込み."""
        file_path = self._resolve_file_path(path)
        
        if not file_path.exists():
            raise StorageNotFoundException(f"ファイルが見つかりません: {path.relative_path}", path)
        
        try:
            return file_path.open("rb")
        except PermissionError:
            raise StoragePermissionException(f"読み込み権限エラー: {path.relative_path}", path)
        except OSError as e:
            raise StorageException(f"ストリーム読み込みエラー: {e}", path)
    
    def write(self, path: StoragePath, content: bytes) -> None:
        """ファイルに内容を書き込み."""
        file_path = self._resolve_file_path(path)
        
        # 親ディレクトリを作成
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            file_path.write_bytes(content)
        except PermissionError:
            raise StoragePermissionException(f"書き込み権限エラー: {path.relative_path}", path)
        except OSError as e:
            raise StorageException(f"書き込みエラー: {e}", path)
    
    def write_stream(self, path: StoragePath, stream: IO[bytes]) -> None:
        """ストリーミングでファイルを書き込み."""
        file_path = self._resolve_file_path(path)
        
        # 親ディレクトリを作成
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with file_path.open("wb") as f:
                shutil.copyfileobj(stream, f)
        except PermissionError:
            raise StoragePermissionException(f"書き込み権限エラー: {path.relative_path}", path)
        except OSError as e:
            raise StorageException(f"ストリーム書き込みエラー: {e}", path)
    
    def copy(self, source: StoragePath, destination: StoragePath) -> None:
        """ファイルをコピー."""
        source_path = self._resolve_file_path(source)
        dest_path = self._resolve_file_path(destination)
        
        if not source_path.exists():
            raise StorageNotFoundException(f"コピー元ファイルが見つかりません: {source.relative_path}", source)
        
        # 親ディレクトリを作成
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            shutil.copy2(source_path, dest_path)
        except PermissionError:
            raise StoragePermissionException(f"コピー権限エラー", source)
        except OSError as e:
            raise StorageException(f"コピーエラー: {e}", source)
    
    def move(self, source: StoragePath, destination: StoragePath) -> None:
        """ファイルを移動."""
        source_path = self._resolve_file_path(source)
        dest_path = self._resolve_file_path(destination)
        
        if not source_path.exists():
            raise StorageNotFoundException(f"移動元ファイルが見つかりません: {source.relative_path}", source)
        
        # 親ディレクトリを作成
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            shutil.move(str(source_path), str(dest_path))
        except PermissionError:
            raise StoragePermissionException(f"移動権限エラー", source)
        except OSError as e:
            raise StorageException(f"移動エラー: {e}", source)
    
    def delete(self, path: StoragePath) -> None:
        """ファイルを削除."""
        file_path = self._resolve_file_path(path)
        
        if not file_path.exists():
            # 削除対象が存在しない場合は正常終了
            return
        
        try:
            file_path.unlink()
        except PermissionError:
            raise StoragePermissionException(f"削除権限エラー: {path.relative_path}", path)
        except OSError as e:
            raise StorageException(f"削除エラー: {e}", path)
    
    def list_objects(self, path_prefix: StoragePath) -> Iterator[StorageMetadata]:
        """プレフィックス配下のファイル一覧を取得."""
        prefix_path = self._resolve_file_path(path_prefix)
        
        # プレフィックスがディレクトリでない場合、親ディレクトリを取得
        if prefix_path.is_file():
            prefix_path = prefix_path.parent
        
        if not prefix_path.exists():
            return
        
        try:
            for file_path in prefix_path.rglob("*"):
                if file_path.is_file():
                    # 相対パスを計算
                    if self._configuration and self._configuration.base_path:
                        base = Path(self._configuration.base_path)
                        try:
                            relative_path = str(file_path.relative_to(base))
                        except ValueError:
                            # ベースパスの外にある場合はスキップ
                            continue
                    else:
                        relative_path = str(file_path)
                    
                    # ドメインとインテント部分を除去してStoragePathを再構築
                    # 例: "media/original/test/file1.txt" -> "test/file1.txt"
                    path_parts = Path(relative_path).parts
                    if len(path_parts) >= 2:
                        # ドメインとインテント部分をスキップ
                        actual_relative_path = str(Path(*path_parts[2:]))
                    else:
                        actual_relative_path = relative_path
                    
                    # StoragePathを再構築
                    storage_path = StoragePath(
                        domain=path_prefix.domain,
                        intent=path_prefix.intent,
                        relative_path=actual_relative_path,
                        resolution=path_prefix.resolution,
                    )
                    
                    yield self.get_metadata(storage_path)
        except OSError as e:
            raise StorageException(f"一覧取得エラー: {e}", path_prefix)
    
    def generate_presigned_url(
        self, 
        path: StoragePath, 
        expiration_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        """ローカルファイルの場合は file:// URLを返す."""
        file_path = self._resolve_file_path(path)
        
        if not file_path.exists() and method.upper() == "GET":
            raise StorageNotFoundException(f"ファイルが見つかりません: {path.relative_path}", path)
        
        return file_path.as_uri()
    
    def _resolve_file_path(self, path: StoragePath) -> Path:
        """StoragePathからローカルファイルパスを解決."""
        if not self._configuration:
            raise StorageException("Storageが初期化されていません")
        
        full_path = self._path_resolver.resolve_full_path(path, self._configuration)
        return Path(full_path)