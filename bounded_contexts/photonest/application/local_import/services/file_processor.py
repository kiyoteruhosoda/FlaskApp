"""ファイル処理を調整するアプリケーションサービス."""
from __future__ import annotations
from typing import Any, Callable, Dict, Optional, Protocol

from ..dto import FileImportDTO
from bounded_contexts.photonest.domain.local_import.value_objects import (
    FileHash,
    ImportStatus,
    RelativePath,
)
from bounded_contexts.photonest.domain.local_import.services import (
    MediaDuplicateChecker,
    MediaSignature,
    PathCalculator,
)


class MediaRepository(Protocol):
    """メディアリポジトリのプロトコル."""
    
    def find_by_signature(self, signature: MediaSignature) -> Optional[Any]:
        """署名によるメディア検索."""
        ...
    
    def save(self, media: Any) -> None:
        """メディアを保存."""
        ...


class MetadataExtractor(Protocol):
    """メタデータ抽出サービスのプロトコル."""
    
    def extract(self, file_path: str) -> Dict[str, Any]:
        """ファイルからメタデータを抽出."""
        ...


class FileMover(Protocol):
    """ファイル移動サービスのプロトコル."""
    
    def move(self, source: str, destination: str) -> bool:
        """ファイルを移動."""
        ...
    
    def delete(self, file_path: str) -> bool:
        """ファイルを削除."""
        ...


class Logger(Protocol):
    """ロガーのプロトコル."""
    
    def info(self, event: str, message: str, **details: Any) -> None:
        """情報ログ."""
        ...
    
    def warning(self, event: str, message: str, **details: Any) -> None:
        \"\"\"警告ログ."""
        ...
    
    def error(self, event: str, message: str, *, exc_info: bool = False, **details: Any) -> None:
        """エラーログ."""
        ...


class FileProcessor:
    """ファイル処理を調整するアプリケーションサービス.
    
    責務：
    - ファイル単位のインポート処理の調整
    - 重複チェック、メタデータ抽出、ファイル移動の連携
    - 処理結果のDTOへの変換
    """
    
    def __init__(
        self,
        *,
        media_repository: MediaRepository,
        metadata_extractor: MetadataExtractor,
        file_mover: FileMover,
        duplicate_checker: MediaDuplicateChecker,
        path_calculator: PathCalculator,
        logger: Logger,
    ) -> None:
        self._media_repo = media_repository
        self._metadata_extractor = metadata_extractor
        self._file_mover = file_mover
        self._duplicate_checker = duplicate_checker
        self._path_calculator = path_calculator
        self._logger = logger
    
    def process_file(
        self,
        source_path: str,
        import_dir: str,
        originals_dir: str,
        *,
        session_id: Optional[str] = None,
    ) -> FileImportDTO:
        """単一ファイルを処理.
        
        Args:
            source_path: ソースファイルのパス
            import_dir: インポートディレクトリ
            originals_dir: 原本保存ディレクトリ
            session_id: セッションID（ログ用）
            
        Returns:
            処理結果のDTO
        """
        try:
            # 1. メタデータ抽出
            metadata = self._metadata_extractor.extract(source_path)
            
            # 2. 署名作成
            file_hash = FileHash(
                sha256=metadata["hash"],
                size_bytes=metadata["size"],
                perceptual_hash=metadata.get("phash"),
            )
            signature = MediaSignature(
                file_hash=file_hash,
                shot_at=metadata.get("shot_at"),
                width=metadata.get("width"),
                height=metadata.get("height"),
                duration_ms=metadata.get("duration_ms"),
                is_video=metadata.get("is_video", False),
            )
            
            # 3. 重複チェック
            existing_media = self._media_repo.find_by_signature(signature)
            if existing_media:
                self._logger.info(
                    "local_import.file.duplicate",
                    "重複ファイルを検出",
                    media_id=existing_media.id,
                    file_path=source_path,
                    session_id=session_id,
                )
                # 重複の場合はソースを削除
                self._file_mover.delete(source_path)
                return FileImportDTO(
                    ok=True,
                    status=ImportStatus.DUPLICATE.value,
                    media_id=existing_media.id,
                    file_path=source_path,
                )
            
            # 4. 保存先パス計算
            destination_path = self._path_calculator.calculate_storage_path(
                shot_at=metadata.get("shot_at"),
                source_type="local",
                file_hash=file_hash.sha256,
                extension=metadata.get("extension", ""),
            )
            
            # 5. ファイル移動
            full_destination = f"{originals_dir}/{destination_path.value}"
            if not self._file_mover.move(source_path, full_destination):
                raise RuntimeError(f"Failed to move file: {source_path}")
            
            # 6. メディアエンティティ作成・保存
            # （実際の実装では MediaFactory を使う）
            # media = self._media_factory.create_from_metadata(metadata, destination_path)
            # self._media_repo.save(media)
            
            self._logger.info(
                "local_import.file.imported",
                "ファイルをインポート",
                file_path=source_path,
                destination=full_destination,
                session_id=session_id,
            )
            
            return FileImportDTO(
                ok=True,
                status=ImportStatus.IMPORTED.value,
                media_id=None,  # 実際のmedia.idを設定
                file_path=source_path,
            )
            
        except Exception as exc:
            self._logger.error(
                "local_import.file.error",
                f"ファイル処理中にエラー: {str(exc)}",
                file_path=source_path,
                error_type=type(exc).__name__,
                error_message=str(exc),
                session_id=session_id,
                exc_info=True,
            )
            return FileImportDTO(
                ok=False,
                status=ImportStatus.ERROR.value,
                file_path=source_path,
                error_message=str(exc),
            )
