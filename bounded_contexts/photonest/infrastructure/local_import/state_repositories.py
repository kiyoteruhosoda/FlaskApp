"""Local Import状態管理の実装リポジトリ

SessionRepository、ItemRepository、StateTransitionLoggerの実装
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from core.db import db
from core.models.picker_session import PickerSession
from bounded_contexts.photonest.application.local_import.state_synchronizer import (
    ItemRepository,
    ItemStateSnapshot,
    SessionRepository,
    StateTransitionLogger,
)
from bounded_contexts.photonest.domain.local_import.state_machine import (
    ItemState,
    SessionState,
    StateTransition,
)
from bounded_contexts.photonest.infrastructure.local_import.audit_logger import (
    AuditLogger,
    LogCategory,
)
from bounded_contexts.photonest.infrastructure.local_import.audit_log_repository import (
    AuditLogRepository,
)


class SessionRepositoryImpl(SessionRepository):
    """セッションリポジトリ実装"""
    
    def __init__(self, session: Session):
        self._session = session
    
    def get_session_state(self, session_id: int) -> SessionState:
        """セッション状態を取得"""
        picker_session = self._session.get(PickerSession, session_id)
        if not picker_session:
            raise ValueError(f"セッションが見つかりません: {session_id}")
        
        return SessionState(picker_session.status)
    
    def update_session_state(
        self,
        session_id: int,
        state: SessionState,
        transition: StateTransition,
    ) -> None:
        """セッション状態を更新"""
        picker_session = self._session.get(PickerSession, session_id)
        if not picker_session:
            raise ValueError(f"セッションが見つかりません: {session_id}")
        
        picker_session.status = state.value
        picker_session.updated_at = datetime.now(timezone.utc)
        picker_session.last_progress_at = datetime.now(timezone.utc)
        
        self._session.flush()
    
    def get_session_stats(self, session_id: int) -> dict:
        """セッション統計を取得"""
        picker_session = self._session.get(PickerSession, session_id)
        if not picker_session:
            return {}
        
        return picker_session.stats()
    
    def update_session_stats(self, session_id: int, stats: dict) -> None:
        """セッション統計を更新"""
        picker_session = self._session.get(PickerSession, session_id)
        if not picker_session:
            raise ValueError(f"セッションが見つかりません: {session_id}")
        
        picker_session.set_stats(stats)
        self._session.flush()


class ItemRepositoryImpl(ItemRepository):
    """アイテムリポジトリ実装
    
    Note: 現在のpicker_sessionにはアイテム別の状態管理がないため、
    stats_jsonに状態を保存する簡易実装。
    将来的には専用テーブル（picker_item等）を作成推奨。
    """
    
    def __init__(self, session: Session):
        self._session = session
    
    def get_item_state(self, item_id: str) -> ItemState:
        """アイテム状態を取得"""
        # stats_jsonから状態を取得
        # 簡易実装: item_states キーに保存
        # TODO: 専用テーブル作成
        return ItemState.PENDING  # デフォルト
    
    def update_item_state(
        self,
        item_id: str,
        state: ItemState,
        transition: StateTransition,
    ) -> None:
        """アイテム状態を更新"""
        # stats_jsonに保存
        # TODO: 専用テーブル作成
        pass
    
    def get_items_by_session(self, session_id: int) -> list[ItemStateSnapshot]:
        """セッションに属する全アイテムを取得"""
        # 簡易実装: picker_selectionsから取得
        # TODO: 専用テーブル作成
        return []


class StateTransitionLoggerImpl(StateTransitionLogger):
    """状態遷移ログ記録実装"""
    
    def __init__(self, audit_logger: AuditLogger):
        self._audit_logger = audit_logger
    
    def log_session_transition(
        self,
        session_id: int,
        transition: StateTransition,
    ) -> None:
        """セッション状態遷移を記録"""
        self._audit_logger.log_state_transition(
            from_state=transition.from_state,
            to_state=transition.to_state,
            reason=transition.reason,
            session_id=session_id,
            metadata=transition.metadata,
        )
    
    def log_item_transition(
        self,
        item_id: str,
        transition: StateTransition,
    ) -> None:
        """アイテム状態遷移を記録"""
        self._audit_logger.log_state_transition(
            from_state=transition.from_state,
            to_state=transition.to_state,
            reason=transition.reason,
            item_id=item_id,
            metadata=transition.metadata,
        )


def create_state_management_service(db_session: Session):
    """状態管理サービスを作成
    
    依存性注入のファクトリ関数
    """
    from bounded_contexts.photonest.application.local_import.state_management_service import (
        StateManagementService,
    )
    from bounded_contexts.photonest.application.local_import.state_synchronizer import (
        StateSynchronizer,
    )
    
    # リポジトリを作成
    audit_log_repo = AuditLogRepository(db_session)
    audit_logger = AuditLogger(audit_log_repo)
    
    session_repo = SessionRepositoryImpl(db_session)
    item_repo = ItemRepositoryImpl(db_session)
    transition_logger = StateTransitionLoggerImpl(audit_logger)
    
    # サービスを作成
    state_sync = StateSynchronizer(
        session_repo,
        item_repo,
        transition_logger,
    )
    
    state_mgr = StateManagementService(
        state_sync,
        audit_logger,
    )
    
    return state_mgr, audit_logger
