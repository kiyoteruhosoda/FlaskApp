"""Phase 3: Local Import完全統合版（with文による状態管理）

このファイルはPhase 3実装の参考実装です。
既存のuse_case.pyを置き換える際に使用してください。
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.db import db
from core.models.picker_session import PickerSession
from core.models.photo_models import PickerSelection

from features.photonest.domain.local_import.import_result import ImportTaskResult
from features.photonest.domain.local_import.state_machine import SessionState, ItemState
from features.photonest.infrastructure.local_import.repositories import (
    create_state_management_service,
)
from features.photonest.infrastructure.local_import.logging_integration import (
    log_with_audit,
    log_performance,
)
from .results import build_thumbnail_task_snapshot


class LocalImportUseCasePhase3:
    """Phase 3: 状態管理を統合したローカルインポートユースケース"""

    def __init__(
        self,
        *,
        db,
        logger,
        session_service,
        scanner,
        queue_processor,
    ) -> None:
        self._db = db
        self._logger = logger
        self._session_service = session_service
        self._scanner = scanner
        self._queue_processor = queue_processor

    def execute(
        self,
        *,
        session_id: Optional[str],
        import_dir: str,
        originals_dir: str,
        celery_task_id: Optional[str] = None,
        task_instance=None,
    ) -> Dict[str, Any]:
        """Phase 3: with文による完全統合版の実行"""
        
        start_time = time.perf_counter()
        
        # 状態管理サービスを初期化
        state_mgr, _ = create_state_management_service(db.session)
        
        result = ImportTaskResult(
            session_id=session_id,
            celery_task_id=celery_task_id,
        )

        session = self._load_or_create_session(session_id, result, celery_task_id)
        if session is None and not result.ok:
            return result.to_dict()

        active_session_id = session.session_id if session else session_id
        session_db_id = session.id if session else None

        # Phase 3: セッション状態を自動管理
        try:
            # PENDING -> EXPANDING
            if session_db_id:
                state_mgr.transition_session(
                    session_db_id,
                    SessionState.EXPANDING,
                    reason="ファイルスキャン開始",
                )

            # ディレクトリチェック
            if not os.path.exists(import_dir):
                result.add_error(f"取り込みディレクトリが存在しません: {import_dir}")
                if session_db_id:
                    state_mgr.transition_session(
                        session_db_id,
                        SessionState.FAILED,
                        reason="取り込みディレクトリ不在",
                    )
                return result.to_dict()

            if not os.path.exists(originals_dir):
                result.add_error(f"保存先ディレクトリが存在しません: {originals_dir}")
                if session_db_id:
                    state_mgr.transition_session(
                        session_db_id,
                        SessionState.FAILED,
                        reason="保存先ディレクトリ不在",
                    )
                return result.to_dict()

            # ファイルスキャン
            files = self._scanner.scan(import_dir, session_id=active_session_id)
            
            self._logger.info(
                "local_import.scan.complete",
                f"取り込み対象ファイルのスキャンが完了: {len(files)}件",
                total=len(files),
                session_id=active_session_id,
            )

            if len(files) == 0:
                result.add_error("取り込み対象ファイルがありません")
                if session_db_id:
                    state_mgr.transition_session(
                        session_db_id,
                        SessionState.CANCELED,
                        reason="対象ファイルなし",
                    )
                return result.to_dict()

            # EXPANDING -> PROCESSING
            if session_db_id:
                state_mgr.transition_session(
                    session_db_id,
                    SessionState.PROCESSING,
                    reason=f"{len(files)}個のファイルを処理開始",
                )

            # キューに登録
            enqueued_count = self._queue_processor.enqueue(
                session,
                files,
                active_session_id=active_session_id,
                celery_task_id=celery_task_id,
            )

            # Phase 3: 各ファイル処理時に状態管理を使用
            # （queue_processorの実装でprocess_itemコンテキストを使用）
            self._queue_processor.process(
                session,
                import_dir=import_dir,
                originals_dir=originals_dir,
                result=result,
                active_session_id=active_session_id,
                celery_task_id=celery_task_id,
                task_instance=task_instance,
                duplicate_regeneration="regenerate",
                # Phase 3用オプション: 状態管理を有効化
                use_state_management=True,
                state_manager=state_mgr,
            )

            # 処理完了
            if session_db_id:
                # 結果に応じて最終状態を決定
                snapshot = state_mgr.get_session_snapshot(session_db_id)
                
                if result.failed > 0 and result.success == 0:
                    # 全て失敗
                    state_mgr.transition_session(
                        session_db_id,
                        SessionState.FAILED,
                        reason=f"全ファイル失敗: {result.failed}件",
                    )
                elif result.failed > result.success:
                    # 失敗が多い
                    state_mgr.transition_session(
                        session_db_id,
                        SessionState.ERROR,
                        reason=f"多数の失敗: 成功{result.success}件, 失敗{result.failed}件",
                    )
                else:
                    # 成功
                    state_mgr.transition_session(
                        session_db_id,
                        SessionState.IMPORTED,
                        reason=f"処理完了: 成功{result.success}件, 失敗{result.failed}件",
                    )

        except Exception as exc:
            result.add_error(f"取り込み処理でエラーが発生しました: {exc}")
            
            if session_db_id:
                state_mgr.transition_session(
                    session_db_id,
                    SessionState.FAILED,
                    reason=f"例外発生: {type(exc).__name__}",
                )
            
            self._logger.error(
                "local_import.task.failed",
                "予期しないエラーが発生",
                session_id=active_session_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
                exc_info=True,
            )
        finally:
            try:
                self._scanner.cleanup()
            except Exception:
                pass

        # パフォーマンスログ
        duration_ms = (time.perf_counter() - start_time) * 1000
        log_performance(
            "local_import_task",
            duration_ms,
            session_id=active_session_id,
            total_files=result.processed,
            success_count=result.success,
            failed_count=result.failed,
        )

        summary_payload = result.to_dict()

        self._logger.info(
            "local_import.task.summary",
            f"ローカルインポートタスクが完了: {result.success}成功, {result.failed}失敗",
            ok=result.ok,
            processed=result.processed,
            session_id=result.session_id,
        )

        return summary_payload

    def _load_or_create_session(
        self,
        session_id: Optional[str],
        result: ImportTaskResult,
        celery_task_id: Optional[str],
    ):
        """セッション読み込みまたは作成"""
        if session_id:
            try:
                session = PickerSession.query.filter_by(session_id=session_id).first()
                if session:
                    return session
                
                self._logger.warning(
                    "local_import.session.not_found",
                    f"指定されたセッションが見つかりません: {session_id}",
                )
                result.add_error(f"セッションが見つかりません: {session_id}")
                return None
                
            except Exception as exc:
                self._logger.error(
                    "local_import.session.load_error",
                    "セッション読み込み中にエラー",
                    error=str(exc),
                    exc_info=True,
                )
                result.add_error(f"セッション読み込みエラー: {exc}")
                return None
        
        # 新規セッション作成
        try:
            session = PickerSession(
                session_id=f"local_import_{uuid.uuid4().hex[:8]}",
                status="pending",
            )
            db.session.add(session)
            db.session.commit()
            
            self._logger.info(
                "local_import.session.created",
                f"新しいセッションを作成: {session.session_id}",
            )
            
            return session
            
        except Exception as exc:
            self._logger.error(
                "local_import.session.create_error",
                "セッション作成中にエラー",
                error=str(exc),
                exc_info=True,
            )
            result.add_error(f"セッション作成エラー: {exc}")
            return None


# Phase 3使用例
"""
使用方法:

1. 既存のLocalImportUseCaseをこのPhase3版に置き換える

2. queue_processor.process()にuse_state_managementフラグを追加

3. 各ファイル処理で状態管理コンテキストを使用:
   
   with state_manager.process_item(item_id, file_path, session_id) as ctx:
       # 自動的にPENDING -> ANALYZING に遷移
       
       analysis = analyze_file(file_path)
       
       # 明示的に状態遷移
       state_manager.transition_item(ctx, ItemState.CHECKING, "重複チェック")
       
       if is_duplicate:
           state_manager.transition_item(ctx, ItemState.SKIPPED, "重複")
           return
       
       # ファイル移動
       state_manager.transition_item(ctx, ItemState.MOVING, "ファイル移動")
       move_file(...)
       
       # 成功時は自動的にIMPORTEDに遷移
       # エラー時は自動的にFAILEDに遷移

利点:
- 状態遷移が自動化される
- エラーハンドリングが統一される
- ログとパフォーマンス計測が自動化される
- 整合性チェックが自動で行われる
"""
