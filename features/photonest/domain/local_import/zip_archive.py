"""ローカルインポートで利用するZIPアーカイブ関連処理。"""

from __future__ import annotations

import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Dict, Iterable, List, Optional, Set

from core.storage_service import StorageService
from domain.storage import StorageDomain

class ZipExtractionError(Exception):
    """ZIP展開処理で致命的なエラーが発生した場合に送出。"""


class ZipArchiveService:
    """ZIPアーカイブを取り扱うドメインサービス。"""

    def __init__(
        self,
        log_info: Callable[..., None],
        log_warning: Callable[..., None],
        log_error: Callable[..., None],
        supported_extensions: Iterable[str],
        storage_service: StorageService,
    ) -> None:
        self._log_info = log_info
        self._log_warning = log_warning
        self._log_error = log_error
        self._supported_extensions = {ext.lower() for ext in supported_extensions}
        self._storage = storage_service
        self._extracted_directories: List[str] = []
        self._base_directory: Optional[Path] = None
        self._tags_by_extracted_path: Dict[str, List[str]] = {}
        self._files_by_directory: Dict[str, Set[str]] = {}

    def _zip_extraction_base_dir(self) -> Path:
        if self._base_directory is not None:
            return self._base_directory

        try:
            area = self._storage.for_domain(StorageDomain.MEDIA_IMPORT)
            base_path = area.ensure_base()
        except KeyError:
            base_path = None

        if base_path:
            extraction_root = Path(self._storage.join(base_path, "_zip"))
            self._storage.ensure_directory(str(extraction_root))
        else:
            fallback = Path(tempfile.gettempdir()) / "local_import_zip"
            self._storage.ensure_directory(fallback)
            extraction_root = Path(fallback)

        self._base_directory = extraction_root
        return extraction_root

    def _register_extracted_directory(self, path: Path) -> None:
        directory = str(path)
        self._extracted_directories.append(directory)
        self._files_by_directory.setdefault(directory, set())

    def cleanup(self) -> None:
        while self._extracted_directories:
            dir_path = self._extracted_directories.pop()
            try:
                self._storage.remove_tree(dir_path)
            except FileNotFoundError:
                pass
            except Exception as exc:  # pragma: no cover - unexpected
                self._log_warning(
                    "local_import.zip.cleanup_failed",
                    "ZIP展開ディレクトリの削除に失敗",
                    directory=str(dir_path),
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            finally:
                extracted = self._files_by_directory.pop(str(dir_path), set())
                for file_path in extracted:
                    self._tags_by_extracted_path.pop(file_path, None)

    def extract(self, zip_path: str, *, session_id: Optional[str] = None) -> List[str]:
        extracted_files: List[str] = []
        archive_path = Path(zip_path)
        extraction_dir = (
            self._zip_extraction_base_dir() / f"{archive_path.stem}_{uuid.uuid4().hex}"
        )
        self._storage.ensure_directory(str(extraction_dir))
        self._register_extracted_directory(extraction_dir)

        should_remove_archive = False

        try:
            with zipfile.ZipFile(zip_path) as archive:
                should_remove_archive = True
                for member in archive.infolist():
                    if member.is_dir():
                        continue

                    normalized_name = (member.filename or "").replace("\\", "/")
                    member_path = PurePosixPath(normalized_name)
                    if member_path.is_absolute() or any(part == ".." for part in member_path.parts):
                        self._log_warning(
                            "local_import.zip.unsafe_member",
                            "ZIP内の危険なパスをスキップ",
                            zip_path=zip_path,
                            member=member.filename,
                            session_id=session_id,
                        )
                        continue

                    if member_path.suffix.lower() not in self._supported_extensions:
                        continue

                    target_path = extraction_dir.joinpath(*member_path.parts)
                    self._storage.ensure_directory(str(target_path.parent))

                    with archive.open(member) as src, self._storage.open(
                        str(target_path), "wb"
                    ) as dst:
                        shutil.copyfileobj(src, dst)

                    extracted_file = str(target_path)
                    extracted_files.append(extracted_file)
                    self._files_by_directory[str(extraction_dir)].add(extracted_file)

                    raw_tags = [
                        part.strip()
                        for part in member_path.parts[:-1]
                        if part and part not in {".", ".."}
                    ]
                    seen: Set[str] = set()
                    ordered_tags: List[str] = []
                    for tag in raw_tags:
                        normalized = tag.strip()
                        if not normalized:
                            continue
                        key = normalized.lower()
                        if key in seen:
                            continue
                        seen.add(key)
                        ordered_tags.append(normalized)
                    if ordered_tags:
                        self._tags_by_extracted_path[extracted_file] = ordered_tags

                    self._log_info(
                        "local_import.zip.member_extracted",
                        "ZIP内のファイルを抽出",
                        session_id=session_id,
                        status="extracted",
                        zip_path=zip_path,
                        member=member.filename,
                        extracted_path=extracted_file,
                    )

        except zipfile.BadZipFile as exc:
            self._log_error(
                "local_import.zip.invalid",
                "ZIPファイルの展開に失敗",
                zip_path=zip_path,
                error_type=type(exc).__name__,
                error_message=str(exc),
                session_id=session_id,
            )
        except Exception as exc:
            self._log_error(
                "local_import.zip.extract_failed",
                "ZIPファイル展開中にエラーが発生",
                zip_path=zip_path,
                error_type=type(exc).__name__,
                error_message=str(exc),
                exc_info=True,
                session_id=session_id,
            )
        else:
            if extracted_files:
                self._log_info(
                    "local_import.zip.extracted",
                    "ZIPファイルを展開",
                    zip_path=zip_path,
                    extracted_count=len(extracted_files),
                    extraction_dir=str(extraction_dir),
                    session_id=session_id,
                    status="extracted",
                )
            else:
                self._log_warning(
                    "local_import.zip.no_supported_files",
                    "ZIPファイルに取り込み対象ファイルがありません",
                    zip_path=zip_path,
                    session_id=session_id,
                    status="skipped",
                )

        if should_remove_archive and self._storage.exists(zip_path):
            try:
                self._storage.remove(zip_path)
                self._log_info(
                    "local_import.zip.removed",
                    "ZIPファイルを削除",
                    zip_path=zip_path,
                    session_id=session_id,
                    status="cleaned",
                )
            except OSError as exc:
                self._log_warning(
                    "local_import.zip.remove_failed",
                    "ZIPファイルの削除に失敗",
                    zip_path=zip_path,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    session_id=session_id,
                    status="warning",
                )

        return extracted_files

    def tags_for(self, extracted_path: str) -> List[str]:
        """Return tag candidates derived from ZIP member directories."""

        if not extracted_path:
            return []

        normalized_path = str(Path(extracted_path))
        tags = self._tags_by_extracted_path.get(normalized_path)
        if not tags:
            return []
        return list(tags)


__all__ = ["ZipArchiveService", "ZipExtractionError"]

