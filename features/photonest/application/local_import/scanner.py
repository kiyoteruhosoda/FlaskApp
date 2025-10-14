"""ローカルインポートの入力ディレクトリを走査するサービス."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Optional

from features.photonest.domain.local_import.logging import file_log_context


class ImportDirectoryScanner:
    """取り込み対象ファイルを抽出する."""

    def __init__(
        self,
        *,
        logger,
        zip_service,
        supported_extensions: Iterable[str],
    ) -> None:
        self._logger = logger
        self._zip_service = zip_service
        self._supported_extensions = {ext.lower() for ext in supported_extensions}

    def scan(self, import_dir: str, *, session_id: Optional[str] = None) -> List[str]:
        files: List[str] = []
        if not os.path.exists(import_dir):
            return files

        for root, _, filenames in os.walk(import_dir):
            for filename in filenames:
                file_path = os.path.join(root, filename)
                file_extension = Path(filename).suffix.lower()
                file_context = file_log_context(file_path, filename)

                if file_extension in self._supported_extensions:
                    files.append(file_path)
                    self._logger.info(
                        "local_import.scan.file_added",
                        "取り込み対象ファイルを検出",
                        session_id=session_id,
                        status="scanning",
                        **file_context,
                        extension=file_extension,
                    )
                elif file_extension == ".zip":
                    self._logger.info(
                        "local_import.scan.zip_detected",
                        "ZIPファイルを検出",
                        session_id=session_id,
                        status="processing",
                        zip_path=file_path,
                    )
                    extracted = self._zip_service.extract(
                        file_path, session_id=session_id
                    )
                    files.extend(extracted)
                else:
                    self._logger.info(
                        "local_import.scan.unsupported",
                        "サポート対象外のファイルをスキップ",
                        session_id=session_id,
                        status="skipped",
                        **file_context,
                        extension=file_extension,
                    )

        return files

    def cleanup(self) -> None:
        self._zip_service.cleanup()
