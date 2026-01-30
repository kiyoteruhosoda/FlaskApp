"""Local Import状態同期サービス

セッション状態とアイテム状態の同期を管理します。
状態遷移の記録とDB保存を担当します。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Protocol

from bounded_contexts.photonest.domain.local_import.state_machine import (
    ItemState,
    ItemStateMachine,
    SessionState,
    SessionStateMachine,
    StateConsistencyValidator,
    StateTransition,
)

logger = logging.getLogger(__name__)


@dataclass
class SessionStateSnapshot:
    """セッション状態のスナップショット"""
    
    session_id: int
    state: SessionState
    item_count: int
    pending_count: int
    processing_count: int
    success_count: int
    failed_count: int
    last_updated: datetime


@dataclass
class ItemStateSnapshot:
    """アイテム状態のスナップショット"""
    
    item_id: str
    state: ItemState
    file_path: str
    error_message: Optional[str] = None
    last_updated: Optional[datetime] = None


class SessionRepository(Protocol):
    """セッションリポジトリインターフェース"""
    
    def get_session_state(self, session_id: int) -> SessionState:
        """セッション状態を取得"""
        ...
    
    def update_session_state(
        self,
        session_id: int,
        state: SessionState,
        transition: StateTransition,
    ) -> None:
        """セッション状態を更新"""
        ...
    
    def get_session_stats(self, session_id: int) -> dict:
        """セッション統計を取得"""
        ...
    
    def update_session_stats(self, session_id: int, stats: dict) -> None:
        """セッション統計を更新"""
        ...


class ItemRepository(Protocol):
    """アイテムリポジトリインターフェース"""
    
    def get_item_state(self, item_id: str) -> ItemState:
        """アイテム状態を取得"""
        ...
    
    def update_item_state(
        self,
        item_id: str,
        state: ItemState,
        transition: StateTransition,
    ) -> None:
        """アイテム状態を更新"""
        ...
    
    def get_items_by_session(self, session_id: int) -> list[ItemStateSnapshot]:
        """セッションに属する全アイテムを取得"""
        ...


class StateTransitionLogger(Protocol):
    """状態遷移ログ記録インターフェース"""
    
    def log_session_transition(
        self,
        session_id: int,
        transition: StateTransition,
    ) -> None:
        """セッション状態遷移を記録"""
        ...
    
    def log_item_transition(
        self,
        item_id: str,
        transition: StateTransition,
    ) -> None:
        """アイテム状態遷移を記録"""
        ...


class StateSynchronizer:
    """状態同期サービス
    
    セッション状態とアイテム状態の同期を管理します。
    状態遷移の検証、記録、DB保存を一元的に行います。
    """
    
    def __init__(
        self,
        session_repo: SessionRepository,
        item_repo: ItemRepository,
        transition_logger: StateTransitionLogger,
    ):
        self._session_repo = session_repo
        self._item_repo = item_repo
        self._transition_logger = transition_logger
    
    def transition_session(
        self,
        session_id: int,
        target_state: SessionState,
        reason: str,
        metadata: Optional[dict] = None,
    ) -> StateTransition:
        """セッション状態を遷移
        
        Args:
            session_id: セッションID
            target_state: 遷移先の状態
            reason: 遷移理由
            metadata: 追加メタデータ
            
        Returns:
            StateTransition: 遷移記録
            
        Raises:
            ValueError: 不正な遷移の場合
        """
        # 現在の状態を取得
        current_state = self._session_repo.get_session_state(session_id)
        
        # 状態遷移機械で検証
        state_machine = SessionStateMachine(current_state)
        transition = state_machine.transition(target_state, reason, metadata)
        
        # DB更新
        self._session_repo.update_session_state(session_id, target_state, transition)
        
        # ログ記録
        self._transition_logger.log_session_transition(session_id, transition)
        
        logger.info(
            "セッション状態遷移",
            extra={
                "session_id": session_id,
                "from_state": transition.from_state,
                "to_state": transition.to_state,
                "reason": reason,
                "metadata": metadata or {},
            },
        )
        
        return transition
    
    def transition_item(
        self,
        item_id: str,
        target_state: ItemState,
        reason: str,
        metadata: Optional[dict] = None,
    ) -> StateTransition:
        """アイテム状態を遷移
        
        Args:
            item_id: アイテムID
            target_state: 遷移先の状態
            reason: 遷移理由
            metadata: 追加メタデータ
            
        Returns:
            StateTransition: 遷移記録
            
        Raises:
            ValueError: 不正な遷移の場合
        """
        # 現在の状態を取得
        current_state = self._item_repo.get_item_state(item_id)
        
        # 状態遷移機械で検証
        state_machine = ItemStateMachine(current_state)
        transition = state_machine.transition(target_state, reason, metadata)
        
        # DB更新
        self._item_repo.update_item_state(item_id, target_state, transition)
        
        # ログ記録
        self._transition_logger.log_item_transition(item_id, transition)
        
        logger.info(
            "アイテム状態遷移",
            extra={
                "item_id": item_id,
                "from_state": transition.from_state,
                "to_state": transition.to_state,
                "reason": reason,
                "metadata": metadata or {},
            },
        )
        
        return transition
    
    def sync_session_with_items(self, session_id: int) -> SessionStateSnapshot:
        """セッション状態をアイテム状態と同期
        
        全アイテムの状態を集計し、セッション状態を適切に更新します。
        
        Args:
            session_id: セッションID
            
        Returns:
            SessionStateSnapshot: 更新後のセッション状態
        """
        # アイテム状態を取得
        items = self._item_repo.get_items_by_session(session_id)
        
        # 統計を計算
        stats = self._calculate_stats(items)
        
        # セッション統計を更新
        self._session_repo.update_session_stats(session_id, stats)
        
        # 現在のセッション状態を取得
        current_session_state = self._session_repo.get_session_state(session_id)
        
        # 状態遷移が必要か判定
        target_state = self._determine_session_state(current_session_state, stats)
        
        # 状態が変わる場合は遷移
        if target_state != current_session_state:
            reason = self._generate_transition_reason(stats)
            try:
                self.transition_session(
                    session_id,
                    target_state,
                    reason,
                    metadata={"stats": stats},
                )
            except ValueError as e:
                logger.warning(
                    f"セッション状態の自動遷移に失敗: {e}",
                    extra={
                        "session_id": session_id,
                        "current_state": current_session_state.value,
                        "target_state": target_state.value,
                        "stats": stats,
                    },
                )
        
        # スナップショットを返す
        return SessionStateSnapshot(
            session_id=session_id,
            state=self._session_repo.get_session_state(session_id),
            item_count=stats["total"],
            pending_count=stats["pending"],
            processing_count=stats["processing"],
            success_count=stats["success"],
            failed_count=stats["failed"],
            last_updated=datetime.now(timezone.utc),
        )
    
    def validate_consistency(self, session_id: int) -> dict:
        """状態の整合性を検証
        
        Args:
            session_id: セッションID
            
        Returns:
            dict: 検証結果
        """
        # セッション状態を取得
        session_state = self._session_repo.get_session_state(session_id)
        
        # アイテム状態を取得
        items = self._item_repo.get_items_by_session(session_id)
        item_states = {item.item_id: item.state for item in items}
        
        # 整合性チェック
        result = StateConsistencyValidator.validate(session_state, item_states)
        
        # 不整合がある場合はログ出力
        if not result.is_consistent:
            logger.error(
                "状態の不整合を検出",
                extra={
                    "session_id": session_id,
                    "issues": result.issues,
                    "recommendations": result.recommendations,
                    "session_state": session_state.value,
                    "item_count": len(items),
                },
            )
        
        return result.to_dict()
    
    @staticmethod
    def _calculate_stats(items: list[ItemStateSnapshot]) -> dict:
        """アイテム統計を計算"""
        total = len(items)
        pending = sum(1 for item in items if item.state == ItemState.PENDING)
        processing = sum(1 for item in items if item.state.is_processing())
        success = sum(1 for item in items if item.state.is_success())
        failed = sum(1 for item in items if item.state == ItemState.FAILED)
        skipped = sum(1 for item in items if item.state == ItemState.SKIPPED)
        
        return {
            "total": total,
            "pending": pending,
            "processing": processing,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "success_rate": success / total if total > 0 else 0,
        }
    
    @staticmethod
    def _determine_session_state(
        current_state: SessionState,
        stats: dict,
    ) -> SessionState:
        """アイテム統計からセッション状態を決定"""
        total = stats["total"]
        processing = stats["processing"]
        success = stats["success"]
        failed = stats["failed"]
        
        # 終了状態の場合は変更しない
        if current_state.is_terminal():
            return current_state
        
        # アイテムがない場合
        if total == 0:
            return SessionState.READY
        
        # 処理中のアイテムがある場合
        if processing > 0:
            return SessionState.IMPORTING
        
        # 全て完了している場合
        if success + failed == total:
            # 成功率で判定
            success_rate = stats["success_rate"]
            if success_rate >= 0.5:
                return SessionState.IMPORTED
            else:
                return SessionState.FAILED
        
        # その他の場合は現在の状態を維持
        return current_state
    
    @staticmethod
    def _generate_transition_reason(stats: dict) -> str:
        """統計から遷移理由を生成"""
        total = stats["total"]
        success = stats["success"]
        failed = stats["failed"]
        processing = stats["processing"]
        
        if processing > 0:
            return f"{processing}個のアイテムを処理中"
        elif success + failed == total:
            return f"全{total}個のアイテム処理完了（成功: {success}, 失敗: {failed}）"
        else:
            return "アイテム状態の変化に伴う自動遷移"
