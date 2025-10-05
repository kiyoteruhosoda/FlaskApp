"""ローカルファイル取り込みのアプリケーションサービス."""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Protocol

from core.models.photo_models import Media, MediaPlayback
from domain.local_import.entities import ImportFile, ImportOutcome
from domain.local_import.logging import existing_media_destination_context, file_log_context
from domain.local_import.media_entities import (
    build_media_from_analysis,
    build_media_item_from_analysis,
    ensure_exif_for_media,
)


class PlaybackError(RuntimeError):
    """ローカルインポート時の再生資産準備に失敗したことを表す."""


class AnalysisService(Protocol):
    def __call__(self, file_path: str):
        ...


class PostProcessService(Protocol):
    def __call__(self, media, *, logger_override, request_context: Dict[str, Any]):
        ...


class DuplicateChecker(Protocol):
    def __call__(self, file_hash: str, file_size: int) -> Optional[Media]:
        ...


class MetadataRefresher(Protocol):
    def __call__(
        self,
        media: Media,
        *,
        originals_dir: str,
        fallback_path: str,
        file_extension: str,
        session_id: Optional[str] = None,
    ) -> bool:
        ...


class DirectoryResolver(Protocol):
    def __call__(self, config_key: str) -> str:
        ...


class ThumbnailRegenerator(Protocol):
    def __call__(self, media: Media, *, session_id: Optional[str] = None) -> tuple[bool, Optional[str]]:
        ...


class Logger(Protocol):
    def info(self, event: str, message: str, *, session_id: Optional[str] = None, status: Optional[str] = None, **details: Any) -> None:
        ...

    def warning(self, event: str, message: str, *, session_id: Optional[str] = None, status: Optional[str] = None, **details: Any) -> None:
        ...

    def error(self, event: str, message: str, *, session_id: Optional[str] = None, status: Optional[str] = None, exc_info: bool = False, **details: Any) -> None:
        ...


@dataclass(frozen=True)
class PlaybackFailurePolicy:
    recoverable_notes: Iterable[str] = ("ffmpeg_missing", "playback_skipped")

    def is_recoverable(self, note: str) -> bool:
        if not note:
            return False

        normalized = note.lower()
        if normalized in {n.lower() for n in self.recoverable_notes}:
            return True
        return normalized.startswith("ffmpeg_")


class LocalImportFileImporter:
    """単一ファイル取り込みのユースケース."""

    def __init__(
        self,
        *,
        db,
        logger: Logger,
        duplicate_checker: DuplicateChecker,
        metadata_refresher: MetadataRefresher,
        post_process_service: PostProcessService,
        post_process_logger,
        directory_resolver: DirectoryResolver,
        analysis_service: AnalysisService,
        thumbnail_regenerator: ThumbnailRegenerator,
        supported_extensions: Iterable[str],
        playback_policy: Optional[PlaybackFailurePolicy] = None,
    ) -> None:
        self._db = db
        self._logger = logger
        self._duplicate_checker = duplicate_checker
        self._metadata_refresher = metadata_refresher
        self._post_process_service = post_process_service
        self._post_process_logger = post_process_logger
        self._directory_resolver = directory_resolver
        self._analysis_service = analysis_service
        self._thumbnail_regenerator = thumbnail_regenerator
        self._supported_extensions = {ext.lower() for ext in supported_extensions}
        self._playback_policy = playback_policy or PlaybackFailurePolicy()

    def import_file(
        self,
        file_path: str,
        import_dir: str,
        originals_dir: str,
        *,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        source = ImportFile(file_path)
        outcome = ImportOutcome(
            source,
            details={
                "success": False,
                "file_path": file_path,
                "reason": "",
                "media_id": None,
                "media_google_id": None,
                "metadata_refreshed": False,
            },
        )

        file_context = file_log_context(file_path)

        self._logger.info(
            "local_import.file.begin",
            "ローカルファイルの取り込みを開始",
            **file_context,
            import_dir=import_dir,
            originals_dir=originals_dir,
            session_id=session_id,
            status="processing",
        )

        try:
            if not os.path.exists(file_path):
                outcome.mark("missing", reason="ファイルが存在しません")
                self._logger.warning(
                    "local_import.file.missing",
                    "取り込み対象ファイルが見つかりません",
                    **file_context,
                    session_id=session_id,
                    status="missing",
                )
                return outcome.as_dict()

            file_extension = Path(file_path).suffix.lower()
            if file_extension not in self._supported_extensions:
                outcome.mark(
                    "unsupported",
                    reason=f"サポートされていない拡張子: {file_extension}",
                )
                self._logger.warning(
                    "local_import.file.unsupported",
                    "サポート対象外拡張子のためスキップ",
                    **file_context,
                    extension=file_extension,
                    session_id=session_id,
                    status="unsupported",
                )
                return outcome.as_dict()

            file_size = os.path.getsize(file_path)
            if file_size == 0:
                outcome.mark("skipped", reason="ファイルサイズが0です")
                self._logger.warning(
                    "local_import.file.empty",
                    "ファイルサイズが0のためスキップ",
                    **file_context,
                    session_id=session_id,
                    status="skipped",
                )
                return outcome.as_dict()

            analysis = self._analysis_service(file_path)
            existing_media = self._duplicate_checker(
                analysis.file_hash, analysis.file_size
            )
            if existing_media:
                return self._handle_duplicate(
                    outcome,
                    existing_media,
                    file_context,
                    file_path,
                    originals_dir,
                    file_extension,
                    session_id,
                )

            return self._store_new_media(
                outcome,
                analysis,
                file_context,
                file_path,
                originals_dir,
                session_id,
            )
        except Exception as exc:
            self._db.session.rollback()
            self._logger.error(
                "local_import.file.failed",
                "ローカルファイル取り込み中にエラーが発生",
                **file_context,
                error_type=type(exc).__name__,
                error_message=str(exc),
                exc_info=True,
                session_id=session_id,
                status="failed",
            )
            outcome.mark("failed", reason=f"エラー: {str(exc)}")
            self._cleanup_destination(file_context, locals(), session_id)
            return outcome.as_dict()

    def _handle_duplicate(
        self,
        outcome: ImportOutcome,
        existing_media: Media,
        file_context: Dict[str, Any],
        file_path: str,
        originals_dir: str,
        file_extension: str,
        session_id: Optional[str],
    ) -> Dict[str, Any]:
        outcome.details.update(
            {
                "reason": f"重複ファイル (既存ID: {existing_media.id})",
                "media_id": existing_media.id,
                "media_google_id": existing_media.google_media_id,
            }
        )
        outcome.mark("duplicate")

        destination_details = existing_media_destination_context(
            existing_media, originals_dir
        )
        for key in ("imported_path", "imported_filename", "relative_path"):
            value = destination_details.get(key)
            if value:
                outcome.details[key] = value

        refreshed = False
        try:
            refreshed = self._metadata_refresher(
                existing_media,
                originals_dir=originals_dir,
                fallback_path=file_path,
                file_extension=file_extension,
                session_id=session_id,
            )
        except Exception as refresh_exc:
            self._logger.error(
                "local_import.file.duplicate_refresh_failed",
                "重複ファイルのメタデータ更新中にエラーが発生",
                **file_context,
                media_id=existing_media.id,
                **destination_details,
                error_type=type(refresh_exc).__name__,
                error_message=str(refresh_exc),
                exc_info=True,
                session_id=session_id,
            )
        else:
            if refreshed:
                outcome.details["metadata_refreshed"] = True
                outcome.details["reason"] = (
                    f"重複ファイル (既存ID: {existing_media.id}) - メタデータ更新"
                )
                outcome.mark("duplicate_refreshed")
                self._logger.info(
                    "local_import.file.duplicate_refreshed",
                    "重複ファイルから既存メディアのメタデータを更新",
                    **file_context,
                    media_id=existing_media.id,
                    **destination_details,
                    session_id=session_id,
                    status="duplicate_refreshed",
                )
                self._remove_source(file_context, file_path, existing_media, destination_details, session_id)
            else:
                self._logger.info(
                    "local_import.file.duplicate",
                    "重複ファイルを検出したためスキップ",
                    **file_context,
                    media_id=existing_media.id,
                    **destination_details,
                    session_id=session_id,
                    status="duplicate",
                )

        if existing_media.is_video:
            regen_success, regen_error = self._thumbnail_regenerator(
                existing_media,
                session_id=session_id,
            )
            if not regen_success:
                outcome.details["thumbnail_regen_error"] = (
                    regen_error or "重複動画のサムネイル再生成に失敗しました"
                )

        return outcome.as_dict()

    def _remove_source(
        self,
        file_context: Dict[str, Any],
        file_path: str,
        existing_media: Media,
        destination_details: Dict[str, Any],
        session_id: Optional[str],
    ) -> None:
        try:
            os.remove(file_path)
            self._logger.info(
                "local_import.file.duplicate_source_removed",
                "重複ファイルのソースを削除",
                **file_context,
                media_id=existing_media.id,
                **destination_details,
                session_id=session_id,
                status="cleaned",
            )
        except FileNotFoundError:
            pass
        except OSError as cleanup_exc:
            self._logger.warning(
                "local_import.file.duplicate_source_remove_failed",
                "重複ファイル削除に失敗",
                **file_context,
                media_id=existing_media.id,
                **destination_details,
                error_type=type(cleanup_exc).__name__,
                error_message=str(cleanup_exc),
                session_id=session_id,
                status="warning",
            )

    def _store_new_media(
        self,
        outcome: ImportOutcome,
        analysis,
        file_context: Dict[str, Any],
        file_path: str,
        originals_dir: str,
        session_id: Optional[str],
    ) -> Dict[str, Any]:
        is_video = analysis.is_video
        imported_filename = analysis.destination_filename
        rel_path = analysis.relative_path
        dest_path = os.path.join(originals_dir, rel_path)

        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(file_path, dest_path)
        self._logger.info(
            "local_import.file.copied",
            "ファイルを保存先にコピーしました",
            **file_context,
            destination=dest_path,
            imported_path=dest_path,
            imported_filename=imported_filename,
            session_id=session_id,
            status="copied",
        )

        aggregate = build_media_item_from_analysis(analysis)
        self._db.session.add(aggregate.media_item)
        if aggregate.photo_metadata is not None:
            self._db.session.add(aggregate.photo_metadata)
        if aggregate.video_metadata is not None:
            self._db.session.add(aggregate.video_metadata)
        self._db.session.flush()

        media = build_media_from_analysis(
            analysis,
            google_media_id=aggregate.media_item.id,
            relative_path=rel_path,
        )
        self._db.session.add(media)
        self._db.session.flush()

        exif_model = ensure_exif_for_media(media, analysis)
        if exif_model is not None:
            self._db.session.add(exif_model)

        self._db.session.commit()

        post_process_result = self._post_process_service(
            media,
            logger_override=self._post_process_logger,
            request_context={
                "session_id": session_id,
                "source": "local_import",
            },
        )
        if post_process_result is not None:
            outcome.details["post_process"] = post_process_result

        if is_video:
            self._validate_playback(
                media, post_process_result or {}, outcome, file_context, session_id
            )

        os.remove(file_path)
        self._logger.info(
            "local_import.file.source_removed",
            "取り込み完了後に元ファイルを削除",
            **file_context,
            session_id=session_id,
            status="cleaned",
        )

        outcome.details.update(
            {
                "success": True,
                "media_id": media.id,
                "media_google_id": media.google_media_id,
                "reason": "取り込み成功",
                "imported_filename": imported_filename,
                "imported_path": dest_path,
            }
        )
        outcome.mark("success")

        self._logger.info(
            "local_import.file.success",
            "ローカルファイルの取り込みが完了",
            **file_context,
            media_id=media.id,
            relative_path=rel_path,
            imported_path=dest_path,
            imported_filename=imported_filename,
            session_id=session_id,
            status="success",
        )
        return outcome.as_dict()

    def _validate_playback(
        self,
        media: Media,
        post_process_result: Dict[str, Any],
        outcome: ImportOutcome,
        file_context: Dict[str, Any],
        session_id: Optional[str],
    ) -> None:
        playback_result = post_process_result.get("playback") or {}
        if not playback_result.get("ok"):
            note = playback_result.get("note") or "unknown"
            if session_id and self._playback_policy.is_recoverable(note):
                self._logger.warning(
                    "local_import.file.playback_skipped",
                    "動画の再生ファイル生成をスキップ",
                    **file_context,
                    media_id=media.id,
                    note=note,
                    session_id=session_id,
                    status="warning",
                )
                warnings = outcome.details.setdefault("warnings", [])
                warnings.append(f"playback_skipped:{note}")
                return
            raise PlaybackError(
                f"動画の再生ファイル生成に失敗しました (理由: {note})"
            )

        self._db.session.refresh(media)
        if not media.has_playback:
            raise PlaybackError(
                "動画の再生ファイル生成に失敗しました (理由: playback_not_marked)"
            )

        playback_entry = MediaPlayback.query.filter_by(
            media_id=media.id, preset="std1080p"
        ).first()
        if not playback_entry or not playback_entry.rel_path:
            raise PlaybackError(
                "動画の再生ファイル生成に失敗しました (理由: playback_record_missing)"
            )

        play_dir = self._directory_resolver("FPV_NAS_PLAY_DIR")
        playback_path = os.path.join(play_dir, playback_entry.rel_path)
        if not os.path.exists(playback_path):
            raise PlaybackError(
                "動画の再生ファイル生成に失敗しました (理由: playback_file_missing)"
            )

    def _cleanup_destination(
        self,
        file_context: Dict[str, Any],
        local_vars: Dict[str, Any],
        session_id: Optional[str],
    ) -> None:
        dest_path = local_vars.get("dest_path")
        if not dest_path:
            return
        try:
            if os.path.exists(dest_path):
                os.remove(dest_path)
                self._logger.info(
                    "local_import.file.cleanup",
                    "エラー発生時にコピー済みファイルを削除",
                    destination=dest_path,
                    session_id=session_id,
                    status="cleaned",
                )
        except Exception as cleanup_error:
            self._logger.warning(
                "local_import.file.cleanup_failed",
                "エラー発生時のコピー済みファイル削除に失敗",
                destination=dest_path,
                error_type=type(cleanup_error).__name__,
                error_message=str(cleanup_error),
                session_id=session_id,
                status="warning",
            )
