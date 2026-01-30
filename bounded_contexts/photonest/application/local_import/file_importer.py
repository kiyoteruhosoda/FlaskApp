"""ローカルファイル取り込みのアプリケーションサービス."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol

from core.models.photo_models import Media, MediaPlayback, Tag
from core.storage_service import StorageService
from bounded_contexts.photonest.domain.local_import.entities import ImportFile, ImportOutcome
from bounded_contexts.photonest.domain.local_import.logging import existing_media_destination_context, file_log_context
from bounded_contexts.photonest.domain.local_import.media_entities import (
    build_media_from_analysis,
    build_media_item_from_analysis,
    ensure_exif_for_media,
)
from bounded_contexts.photonest.domain.local_import.media_file import MediaFileAnalysis

# Phase 2: 状態管理ログ統合
from bounded_contexts.photonest.infrastructure.local_import.logging_integration import (
    log_file_operation,
    log_duplicate_check,
    log_error_with_actions,
    log_performance,
)


class PlaybackError(RuntimeError):
    """ローカルインポート時の再生資産準備に失敗したことを表す."""


class AnalysisService(Protocol):
    def __call__(self, file_path: str) -> MediaFileAnalysis:
        ...


class PostProcessService(Protocol):
    def __call__(
        self,
        media,
        *,
        logger_override,
        request_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        ...


class DuplicateChecker(Protocol):
    def __call__(self, analysis: MediaFileAnalysis) -> Optional[Media]:
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
    def __call__(
        self,
        media: Media,
        *,
        session_id: Optional[str] = None,
        regeneration_mode: str = "regenerate",
    ) -> tuple[bool, Optional[str]]:
        ...


class TagResolver(Protocol):
    def __call__(self, file_path: str) -> Iterable[str]:
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
    recoverable_notes: Iterable[str] = (
        "ffmpeg_missing",
        "playback_skipped",
        "playback_file_missing",
    )
    session_only_notes: Iterable[str] = ("ffmpeg_missing",)

    def is_recoverable(self, note: str) -> bool:
        if not note:
            return False

        normalized = note.lower()
        if normalized in {n.lower() for n in self.recoverable_notes}:
            return True
        return normalized.startswith("ffmpeg_")

    def requires_session(self, note: str) -> bool:
        normalized = (note or "").lower()
        return normalized in {n.lower() for n in self.session_only_notes}


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
        source_storage: StorageService,
        destination_storage: StorageService,
        playback_policy: Optional[PlaybackFailurePolicy] = None,
        tag_resolver: Optional[TagResolver] = None,
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
        self._source_storage = source_storage
        self._destination_storage = destination_storage
        self._tag_resolver = tag_resolver

    def _copy_to_destination(self, source_path: str, destination_path: str) -> None:
        if self._source_storage is self._destination_storage:
            self._destination_storage.copy(source_path, destination_path)
            return

        with self._source_storage.open(source_path, "rb") as src, self._destination_storage.open(
            destination_path, "wb"
        ) as dst:
            shutil.copyfileobj(src, dst)

    def import_file(
        self,
        file_path: str,
        import_dir: str,
        originals_dir: str,
        *,
        session_id: Optional[str] = None,
        duplicate_regeneration: Optional[str] = None,
        file_task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Phase 2: パフォーマンス計測開始
        import time
        start_time = time.perf_counter()
        item_id = file_task_id or f"item_{hash(file_path)}"
        
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

        file_context = file_log_context(file_path, file_task_id=file_task_id)

        # Phase 2: ファイル処理開始ログ
        log_file_operation(
            "ファイル取り込み開始",
            file_path=file_path,
            operation="import",
            session_id=session_id,
            item_id=item_id,
        )

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
            if not self._source_storage.exists(file_path):
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

            file_size = self._source_storage.size(file_path)
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
            
            # Phase 2: 重複チェックログ
            existing_media = self._duplicate_checker(analysis)
            log_duplicate_check(
                "重複チェック完了",
                file_hash=analysis.file_hash if analysis else "",
                match_type="exact" if existing_media else "none",
                session_id=session_id,
                item_id=item_id,
                is_duplicate=bool(existing_media),
            )
            
            if existing_media:
                result = self._handle_duplicate(
                    outcome,
                    existing_media,
                    file_context,
                    file_path,
                    originals_dir,
                    file_extension,
                    session_id,
                    duplicate_regeneration,
                )
                # Phase 2: パフォーマンスログ（重複）
                duration_ms = (time.perf_counter() - start_time) * 1000
                log_performance(
                    "file_import_duplicate",
                    duration_ms,
                    session_id=session_id,
                    item_id=item_id,
                    file_size_bytes=file_size,
                )
                return result

            result = self._store_new_media(
                outcome,
                analysis,
                file_context,
                file_path,
                originals_dir,
                session_id,
            )
            
            # Phase 2: パフォーマンスログ（成功）
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_performance(
                "file_import_success",
                duration_ms,
                session_id=session_id,
                item_id=item_id,
                file_size_bytes=file_size,
            )
            log_file_operation(
                "ファイル取り込み完了",
                file_path=file_path,
                operation="import",
                session_id=session_id,
                item_id=item_id,
            )
            
            return result
        except Exception as exc:
            self._db.session.rollback()
            
            # Phase 2: エラーログと推奨アクション
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_performance(
                "file_import_failed",
                duration_ms,
                session_id=session_id,
                item_id=item_id,
            )
            
            from bounded_contexts.photonest.application.local_import.troubleshooting import (
                TroubleshootingEngine,
            )
            engine = TroubleshootingEngine()
            diagnosis = engine.diagnose(exc, {"file_path": file_path, "operation": "import"})
            
            log_error_with_actions(
                f"ファイル取り込み失敗: {diagnosis.summary}",
                error=exc,
                recommended_actions=diagnosis.recommended_actions,
                session_id=session_id,
                item_id=item_id,
            )
            
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
        duplicate_regeneration: Optional[str],
    ) -> Dict[str, Any]:
        regen_mode = (duplicate_regeneration or "regenerate").lower()
        if regen_mode not in {"regenerate", "skip"}:
            regen_mode = "regenerate"
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
                destination_details = existing_media_destination_context(
                    existing_media, originals_dir
                )
                for key in ("imported_path", "imported_filename", "relative_path"):
                    value = destination_details.get(key)
                    if value:
                        outcome.details[key] = value
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
            if regen_mode == "skip":
                self._logger.info(
                    "local_import.file.duplicate_video_regen_skipped",
                    "重複動画のサムネイル/再生アセット再生成をスキップ",
                    **file_context,
                    media_id=existing_media.id,
                    session_id=session_id,
                    status="duplicate_regen_skipped",
                )
            else:
                regen_success, regen_error = self._thumbnail_regenerator(
                    existing_media,
                    session_id=session_id,
                    regeneration_mode=regen_mode,
                )
                if not regen_success:
                    outcome.details["thumbnail_regen_error"] = (
                        regen_error or "重複動画のサムネイル再生成に失敗しました"
                    )
                else:
                    outcome.details["thumbnail_regenerated"] = True

        outcome.details["duplicate_regeneration_mode"] = regen_mode

        self._remove_source_file(file_path, file_context, session_id)

        return outcome.as_dict()

    def _resolve_directory_tags(self, file_path: str) -> List[Tag]:
        if not self._tag_resolver:
            return []

        try:
            raw_tags = list(self._tag_resolver(file_path) or [])
        except Exception:  # pragma: no cover - defensive
            return []

        if not raw_tags:
            return []

        normalized: Dict[str, str] = {}
        for candidate in raw_tags:
            if candidate is None:
                continue
            name = str(candidate).strip()
            if not name:
                continue
            key = name.lower()
            if key not in normalized:
                normalized[key] = name

        if not normalized:
            return []

        existing_tags = (
            self._db.session.query(Tag)
            .filter(self._db.func.lower(Tag.name).in_(list(normalized.keys())))
            .all()
        )
        existing_map = {tag.name.lower(): tag for tag in existing_tags}

        resolved: List[Tag] = []
        for key, display in normalized.items():
            tag = existing_map.get(key)
            if tag is None:
                tag = Tag(name=display, attr="source")
                self._db.session.add(tag)
                self._db.session.flush([tag])
            resolved.append(tag)

        return resolved

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
        dest_path = self._destination_storage.join(originals_dir, rel_path)

        self._destination_storage.ensure_parent(dest_path)
        self._copy_to_destination(file_path, dest_path)
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

        directory_tags = self._resolve_directory_tags(file_path)
        if directory_tags:
            for tag in directory_tags:
                if tag not in media.tags:
                    media.tags.append(tag)
            self._db.session.flush()

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

        self._remove_source_file(file_path, file_context, session_id)

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
        self._logger.info(
            "local_import.file.processed_success",
            "ローカルファイルの処理が完了",
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
            error_detail = playback_result.get("error")
            if self._playback_policy.is_recoverable(note):
                if self._playback_policy.requires_session(note) and not session_id:
                    raise PlaybackError(
                        f"動画の再生ファイル生成に失敗しました (理由: {note})"
                    )
                log_details = {
                    **file_context,
                    "media_id": media.id,
                    "note": note,
                    "status": "warning",
                }
                if session_id:
                    log_details["session_id"] = session_id
                if error_detail:
                    log_details["error"] = error_detail

                self._logger.warning(
                    "local_import.file.playback_skipped",
                    "動画の再生ファイル生成をスキップ",
                    **log_details,
                )

                warnings = outcome.details.setdefault("warnings", [])
                warning_token = f"playback_skipped:{note}"
                if warning_token not in warnings:
                    warnings.append(warning_token)
                if error_detail:
                    error_token = f"playback_error:{error_detail}"
                    if error_token not in warnings:
                        warnings.append(error_token)
                    outcome.details.setdefault("playback_error", error_detail)
                outcome.details.setdefault("playback_note", note)
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

        play_dir = self._directory_resolver("MEDIA_PLAYBACK_DIRECTORY")
        playback_path = self._destination_storage.join(play_dir, playback_entry.rel_path)
        if not self._destination_storage.exists(playback_path):
            note = "playback_file_missing"
            if self._playback_policy.requires_session(note) and not session_id:
                raise PlaybackError(
                    f"動画の再生ファイル生成に失敗しました (理由: {note})"
                )

            log_details = {
                **file_context,
                "media_id": media.id,
                "note": note,
                "status": "warning",
                "expected_path": playback_path,
            }
            if session_id:
                log_details["session_id"] = session_id

            self._logger.warning(
                "local_import.file.playback_missing",
                "再生ファイルが見つからなかったため遅延完了として処理",
                **log_details,
            )

            warnings = outcome.details.setdefault("warnings", [])
            warning_token = f"playback_skipped:{note}"
            if warning_token not in warnings:
                warnings.append(warning_token)
            outcome.details.setdefault("playback_note", note)
            outcome.details.setdefault("playback_error", note)
            return

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
            if self._destination_storage.exists(dest_path):
                self._destination_storage.remove(dest_path)
                self._logger.info(
                    "local_import.file.cleanup",
                    "エラー発生時にコピー済みファイルを削除",
                    destination=dest_path,
                    session_id=session_id,
                    status="cleaned",
                )
        except FileNotFoundError:
            pass
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

    def _remove_source_file(
        self,
        file_path: str,
        file_context: Dict[str, Any],
        session_id: Optional[str],
    ) -> None:
        try:
            self._source_storage.remove(file_path)
        except FileNotFoundError:
            self._logger.info(
                "local_import.file.source_missing",
                "取り込み完了後に元ファイルが見つからず削除をスキップ",
                **file_context,
                session_id=session_id,
                status="missing",
            )
            return
        except OSError as remove_error:
            self._logger.warning(
                "local_import.file.source_remove_failed",
                "取り込み完了後の元ファイル削除に失敗",
                error_type=type(remove_error).__name__,
                error_message=str(remove_error),
                **file_context,
                session_id=session_id,
                status="warning",
            )
            return

        self._logger.info(
            "local_import.file.source_removed",
            "取り込み完了後に元ファイルを削除",
            **file_context,
            session_id=session_id,
            status="cleaned",
        )
