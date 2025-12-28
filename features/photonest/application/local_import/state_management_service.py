"""Local Import状態管理サービス

状態遷移、同期、監査を統合的に管理します。
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Generator, Optional

from features.photonest.application.local_import.state_synchronizer import (
    ItemRepository,
    ItemStateSnapshot,
    SessionRepository,
    SessionStateSnapshot,
    StateSynchronizer,
    StateTransitionLogger,
)
from features.photonest.domain.local_import.state_machine import (
    ItemState,
    SessionState,
    StateTransition,
)
from features.photonest.infrastructure.local_import.audit_logger import (
    AuditLogger,
    LogCategory,
    StructuredLogger,
)

logger = logging.getLogger(__name__)


@dataclass
class ItemProcessingContext:
    """アイテム処理コンテキスト
    
    処理中のアイテム情報と状態を保持します。
    """
    
    item_id: str
    file_path: str
    session_id: int
    current_state: ItemState
    start_time: datetime
    structured_logger: StructuredLogger


class StateManagementService:
    """状態管理サービス
    
    Local Import処理の状態管理を一元的に行います。
    - 状態遷移の検証と実行
    - セッション/アイテム状態の同期
    - 構造化ログの記録
    - パフォーマンス計測
    """
    
    def __init__(
        self,
        state_synchronizer: StateSynchronizer,
        audit_logger: AuditLogger,
    ):
        self._sync = state_synchronizer
        self._audit = audit_logger
    
    @contextmanager
    def process_item(
        self,
        item_id: str,
        file_path: str,
        session_id: int,
    ) -> Generator[ItemProcessingContext, None, None]:
        """アイテム処理コンテキスト
        
        with文で使用し、状態遷移とログを自動管理します。
        
        使用例:
            with state_mgr.process_item(item_id, path, session_id) as ctx:
                # 処理...
                ctx.structured_logger.info("処理開始")
                
                # 状態を遷移
                state_mgr.transition_item(ctx, ItemState.CHECKING, "重複チェック開始")
        """
        # 開始時刻
        start_time = datetime.now(timezone.utc)
        
        # 構造化ログを準備
        structured_logger = StructuredLogger(
            self._audit,
            session_id=session_id,
            item_id=item_id,
        )
        
        # PENDING -> ANALYZING に遷移
        try:
            self._sync.transition_item(
                item_id,
                ItemState.ANALYZING,
                reason=f"ファイル処理開始: {file_path}",
            )
        except ValueError as e:
            # 既にANALYZING以降の状態の場合はスキップ
            logger.debug(f"状態遷移スキップ: {e}")
        
        structured_logger.info(
            "アイテム処理開始",
            category=LogCategory.FILE_OPERATION,
            file_path=file_path,
        )
        
        # コンテキストを作成
        current_state = ItemState.ANALYZING
        ctx = ItemProcessingContext(
            item_id=item_id,
            file_path=file_path,
            session_id=session_id,
            current_state=current_state,
            start_time=start_time,
            structured_logger=structured_logger,
        )
        
        try:
            yield ctx
            
            # 正常終了の場合、IMPORTED状態にする（まだ終了状態でない場合）
            if not ctx.current_state.is_terminal():
                self._sync.transition_item(
                    item_id,
                    ItemState.IMPORTED,
                    reason="処理正常完了",
                )
                ctx.current_state = ItemState.IMPORTED
            
            # パフォーマンスログ
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            structured_logger.performance(
                operation_name="item_processing",
                duration_ms=duration_ms,
            )
            
            structured_logger.info(
                "アイテム処理完了",
                category=LogCategory.FILE_OPERATION,
                duration_ms=duration_ms,
            )
            
        except Exception as e:
            # エラーの場合、FAILED状態にする
            try:
                self._sync.transition_item(
                    item_id,
                    ItemState.FAILED,
                    reason=f"処理失敗: {type(e).__name__}",
                    metadata={"error": str(e)},
                )
            except ValueError:
                # 遷移不可の場合はログのみ
                logger.warning(f"FAILED状態への遷移失敗: {e}")
            
            structured_logger.error(
                f"アイテム処理失敗: {e}",
                exception=e,
                is_retryable=True,
            )
            
            raise
        
        finally:
            # セッション状態を同期
            try:
                self._sync.sync_session_with_items(session_id)
            except Exception as e:
                logger.error(f"セッション状態同期失敗: {e}", exc_info=True)
    
    def transition_session(
        self,
        session_id: int,
        target_state: SessionState,
        reason: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """セッション状態を遷移
        
        Args:
            session_id: セッションID
            target_state: 遷移先の状態
            reason: 遷移理由
            metadata: 追加メタデータ
        """
        self._sync.transition_session(session_id, target_state, reason, metadata)
    
    def transition_item(
        self,
        ctx: ItemProcessingContext,
        target_state: ItemState,
        reason: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """アイテム状態を遷移（コンテキスト経由）
        
        Args:
            ctx: アイテム処理コンテキスト
            target_state: 遷移先の状態
            reason: 遷移理由
            metadata: 追加メタデータ
        """
        self._sync.transition_item(ctx.item_id, target_state, reason, metadata)
        ctx.current_state = target_state
    
    def validate_consistency(self, session_id: int) -> dict:
        """状態の整合性を検証
        
        Args:
            session_id: セッションID
            
        Returns:
            dict: 検証結果
        """
        result = self._sync.validate_consistency(session_id)
        
        # 監査ログに記録
        self._audit.log_consistency_check(
            session_id=session_id,
            is_consistent=result["is_consistent"],
            issues=result["issues"],
            recommendations=result["recommendations"],
        )
        
        return result
    
    def get_session_snapshot(self, session_id: int) -> SessionStateSnapshot:
        """セッション状態のスナップショットを取得
        
        Args:
            session_id: セッションID
            
        Returns:
            SessionStateSnapshot: 現在の状態
        """
        return self._sync.sync_session_with_items(session_id)
    
    def create_structured_logger(
        self,
        session_id: Optional[int] = None,
        item_id: Optional[str] = None,
    ) -> StructuredLogger:
        """構造化ロガーを作成
        
        Args:
            session_id: セッションID
            item_id: アイテムID
            
        Returns:
            StructuredLogger: 構造化ロガー
        """
        return StructuredLogger(self._audit, session_id, item_id)


class PerformanceTracker:
    """パフォーマンス計測ユーティリティ"""
    
    def __init__(self, structured_logger: StructuredLogger):
        self._logger = structured_logger
        self._start_time: Optional[float] = None
        self._operation_name: Optional[str] = None
    
    @contextmanager
    def measure(
        self,
        operation_name: str,
        file_size_bytes: Optional[int] = None,
    ) -> Generator[None, None, None]:
        """操作時間を計測
        
        使用例:
            with tracker.measure("duplicate_check"):
                # 処理...
                pass
        """
        start = time.perf_counter()
        
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            
            self._logger.performance(
                operation_name=operation_name,
                duration_ms=duration_ms,
                file_size_bytes=file_size_bytes,
            )


class ErrorHandler:
    """エラーハンドリングユーティリティ"""
    
    def __init__(self, structured_logger: StructuredLogger):
        self._logger = structured_logger
    
    def handle_file_error(
        self,
        error: Exception,
        file_path: str,
        operation: str,
    ) -> None:
        """ファイル操作エラーを処理
        
        Args:
            error: 例外オブジェクト
            file_path: ファイルパス
            operation: 操作名
        """
        error_type = type(error).__name__
        
        # 推奨アクションを生成
        if error_type == "FileNotFoundError":
            actions = [
                f"ファイルが存在するか確認: {file_path}",
                "ファイルが移動または削除されていないか確認",
            ]
        elif error_type == "PermissionError":
            actions = [
                f"ファイルのアクセス権限を確認: {file_path}",
                "他のプロセスがファイルを使用していないか確認",
            ]
        elif error_type == "OSError":
            actions = [
                "ディスク容量を確認",
                f"ファイルシステムの状態を確認: {file_path}",
            ]
        else:
            actions = [
                "エラーの詳細をログで確認",
                "必要に応じて再試行",
            ]
        
        self._logger.error(
            f"{operation}失敗: {file_path}",
            exception=error,
            category=LogCategory.FILE_OPERATION,
            is_retryable=error_type in {"FileNotFoundError", "OSError"},
            recommended_actions=actions,
            file_path=file_path,
            operation=operation,
        )
    
    def handle_db_error(
        self,
        error: Exception,
        operation: str,
        entity_type: str,
        entity_id: Optional[str] = None,
    ) -> None:
        """データベース操作エラーを処理
        
        Args:
            error: 例外オブジェクト
            operation: 操作名
            entity_type: エンティティタイプ
            entity_id: エンティティID
        """
        error_type = type(error).__name__
        
        actions = [
            "データベース接続を確認",
            "トランザクションの状態を確認",
        ]
        
        if error_type == "IntegrityError":
            actions.extend([
                "重複するデータがないか確認",
                "外部キー制約違反がないか確認",
            ])
        
        self._logger.error(
            f"{operation}失敗: {entity_type}",
            exception=error,
            category=LogCategory.DB_OPERATION,
            is_retryable=error_type != "IntegrityError",
            recommended_actions=actions,
            operation=operation,
            entity_type=entity_type,
            entity_id=entity_id,
        )
