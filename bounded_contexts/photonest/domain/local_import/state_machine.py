"""Local Import状態遷移機械

状態遷移を一元管理し、不正な遷移を防止します。
アイテム状態とセッション状態の整合性を保証します。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class SessionState(str, Enum):
    """セッション全体の状態"""
    
    # 初期状態
    PENDING = "pending"           # セッション作成直後
    READY = "ready"               # ファイル選択完了、処理待ち
    
    # 処理中
    EXPANDING = "expanding"       # ディレクトリ展開中
    PROCESSING = "processing"     # ファイル処理中
    ENQUEUED = "enqueued"         # ワーカーキューに投入済み
    IMPORTING = "importing"       # インポート実行中
    
    # 終了状態
    IMPORTED = "imported"         # 正常完了
    CANCELED = "canceled"         # ユーザーによるキャンセル
    EXPIRED = "expired"           # セッション有効期限切れ
    ERROR = "error"               # エラー発生（リトライ不可）
    FAILED = "failed"             # 処理失敗（リトライ可能）
    
    def is_terminal(self) -> bool:
        """終了状態かどうか"""
        return self in {
            SessionState.IMPORTED,
            SessionState.CANCELED,
            SessionState.EXPIRED,
            SessionState.ERROR,
            SessionState.FAILED,
        }
    
    def is_processing(self) -> bool:
        """処理中かどうか"""
        return self in {
            SessionState.EXPANDING,
            SessionState.PROCESSING,
            SessionState.ENQUEUED,
            SessionState.IMPORTING,
        }
    
    def can_cancel(self) -> bool:
        """キャンセル可能かどうか"""
        return not self.is_terminal()


class ItemState(str, Enum):
    """個別アイテムの状態"""
    
    # 初期状態
    PENDING = "pending"           # 処理待ち
    
    # 処理中
    ANALYZING = "analyzing"       # ファイル解析中
    CHECKING = "checking"         # 重複チェック中
    MOVING = "moving"             # ファイル移動中
    UPDATING = "updating"         # DB更新中
    
    # 終了状態
    IMPORTED = "imported"         # 正常インポート完了
    SKIPPED = "skipped"           # スキップ（重複など）
    FAILED = "failed"             # 処理失敗
    
    # 特殊状態
    MISSING = "missing"           # ソースファイルが見つからない
    SOURCE_RESTORED = "source_restored"  # ソース復元済み
    PATH_UPDATED = "path_updated"        # パス更新済み
    WARNING = "warning"                  # 警告あり
    
    def is_terminal(self) -> bool:
        """終了状態かどうか"""
        return self in {
            ItemState.IMPORTED,
            ItemState.SKIPPED,
            ItemState.FAILED,
            ItemState.SOURCE_RESTORED,
            ItemState.PATH_UPDATED,
        }
    
    def is_processing(self) -> bool:
        """処理中かどうか"""
        return self in {
            ItemState.ANALYZING,
            ItemState.CHECKING,
            ItemState.MOVING,
            ItemState.UPDATING,
        }
    
    def is_success(self) -> bool:
        """成功状態かどうか"""
        return self in {
            ItemState.IMPORTED,
            ItemState.SOURCE_RESTORED,
            ItemState.PATH_UPDATED,
        }


@dataclass(frozen=True)
class StateTransition:
    """状態遷移の記録"""
    
    from_state: str
    to_state: str
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """辞書に変換"""
        return {
            "from_state": self.from_state,
            "to_state": self.to_state,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class SessionStateMachine:
    """セッション状態遷移機械
    
    セッション状態の遷移を管理し、不正な遷移を防止します。
    """
    
    # 許可される状態遷移マップ
    _ALLOWED_TRANSITIONS: dict[SessionState, set[SessionState]] = {
        SessionState.PENDING: {
            SessionState.READY,
            SessionState.CANCELED,
            SessionState.EXPIRED,
            SessionState.ERROR,
        },
        SessionState.READY: {
            SessionState.EXPANDING,
            SessionState.PROCESSING,
            SessionState.CANCELED,
            SessionState.ERROR,
        },
        SessionState.EXPANDING: {
            SessionState.PROCESSING,
            SessionState.ENQUEUED,
            SessionState.CANCELED,
            SessionState.ERROR,
            SessionState.FAILED,
        },
        SessionState.PROCESSING: {
            SessionState.ENQUEUED,
            SessionState.IMPORTING,
            SessionState.IMPORTED,
            SessionState.CANCELED,
            SessionState.ERROR,
            SessionState.FAILED,
        },
        SessionState.ENQUEUED: {
            SessionState.IMPORTING,
            SessionState.CANCELED,
            SessionState.ERROR,
            SessionState.FAILED,
        },
        SessionState.IMPORTING: {
            SessionState.IMPORTED,
            SessionState.ERROR,
            SessionState.FAILED,
        },
        # 終了状態からは遷移不可
        SessionState.IMPORTED: set(),
        SessionState.CANCELED: set(),
        SessionState.EXPIRED: set(),
        SessionState.ERROR: set(),
        SessionState.FAILED: {SessionState.PROCESSING},  # リトライ可能
    }
    
    def __init__(self, current_state: SessionState):
        self._current_state = current_state
        self._history: list[StateTransition] = []
    
    @property
    def current_state(self) -> SessionState:
        """現在の状態"""
        return self._current_state
    
    @property
    def history(self) -> list[StateTransition]:
        """状態遷移履歴"""
        return self._history.copy()
    
    def can_transition_to(self, target_state: SessionState) -> bool:
        """指定された状態に遷移可能かどうか"""
        allowed = self._ALLOWED_TRANSITIONS.get(self._current_state, set())
        return target_state in allowed
    
    def transition(
        self,
        target_state: SessionState,
        reason: str,
        metadata: Optional[dict] = None,
    ) -> StateTransition:
        """状態を遷移
        
        Args:
            target_state: 遷移先の状態
            reason: 遷移理由
            metadata: 追加メタデータ
            
        Returns:
            StateTransition: 遷移記録
            
        Raises:
            ValueError: 不正な遷移の場合
        """
        if not self.can_transition_to(target_state):
            raise ValueError(
                f"不正な状態遷移: {self._current_state.value} -> {target_state.value}"
            )
        
        transition = StateTransition(
            from_state=self._current_state.value,
            to_state=target_state.value,
            reason=reason,
            metadata=metadata or {},
        )
        
        self._current_state = target_state
        self._history.append(transition)
        
        return transition
    
    def force_transition(
        self,
        target_state: SessionState,
        reason: str,
        metadata: Optional[dict] = None,
    ) -> StateTransition:
        """状態を強制遷移（検証なし）
        
        緊急時やリカバリー時にのみ使用。
        """
        transition = StateTransition(
            from_state=self._current_state.value,
            to_state=target_state.value,
            reason=f"[FORCED] {reason}",
            metadata=metadata or {},
        )
        
        self._current_state = target_state
        self._history.append(transition)
        
        return transition


class ItemStateMachine:
    """アイテム状態遷移機械
    
    個別アイテムの状態遷移を管理します。
    """
    
    _ALLOWED_TRANSITIONS: dict[ItemState, set[ItemState]] = {
        ItemState.PENDING: {
            ItemState.ANALYZING,
            ItemState.MISSING,
            ItemState.FAILED,
        },
        ItemState.ANALYZING: {
            ItemState.CHECKING,
            ItemState.MISSING,
            ItemState.FAILED,
        },
        ItemState.CHECKING: {
            ItemState.MOVING,
            ItemState.SKIPPED,
            ItemState.FAILED,
        },
        ItemState.MOVING: {
            ItemState.UPDATING,
            ItemState.SOURCE_RESTORED,
            ItemState.FAILED,
        },
        ItemState.UPDATING: {
            ItemState.IMPORTED,
            ItemState.PATH_UPDATED,
            ItemState.WARNING,
            ItemState.FAILED,
        },
        # 終了状態
        ItemState.IMPORTED: set(),
        ItemState.SKIPPED: set(),
        ItemState.FAILED: {ItemState.ANALYZING},  # リトライ可能
        ItemState.MISSING: set(),
        ItemState.SOURCE_RESTORED: set(),
        ItemState.PATH_UPDATED: set(),
        ItemState.WARNING: {ItemState.IMPORTED},  # 警告後も処理続行可能
    }
    
    def __init__(self, current_state: ItemState):
        self._current_state = current_state
        self._history: list[StateTransition] = []
    
    @property
    def current_state(self) -> ItemState:
        """現在の状態"""
        return self._current_state
    
    @property
    def history(self) -> list[StateTransition]:
        """状態遷移履歴"""
        return self._history.copy()
    
    def can_transition_to(self, target_state: ItemState) -> bool:
        """指定された状態に遷移可能かどうか"""
        allowed = self._ALLOWED_TRANSITIONS.get(self._current_state, set())
        return target_state in allowed
    
    def transition(
        self,
        target_state: ItemState,
        reason: str,
        metadata: Optional[dict] = None,
    ) -> StateTransition:
        """状態を遷移"""
        if not self.can_transition_to(target_state):
            raise ValueError(
                f"不正な状態遷移: {self._current_state.value} -> {target_state.value}"
            )
        
        transition = StateTransition(
            from_state=self._current_state.value,
            to_state=target_state.value,
            reason=reason,
            metadata=metadata or {},
        )
        
        self._current_state = target_state
        self._history.append(transition)
        
        return transition


@dataclass(frozen=True)
class StateConsistencyCheck:
    """状態整合性チェック結果"""
    
    is_consistent: bool
    session_state: SessionState
    item_states: dict[str, ItemState]
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """辞書に変換"""
        return {
            "is_consistent": self.is_consistent,
            "session_state": self.session_state.value,
            "item_states": {k: v.value for k, v in self.item_states.items()},
            "issues": self.issues,
            "recommendations": self.recommendations,
        }


class StateConsistencyValidator:
    """状態整合性検証器
    
    セッション状態とアイテム状態の整合性をチェックします。
    """
    
    @staticmethod
    def validate(
        session_state: SessionState,
        item_states: dict[str, ItemState],
    ) -> StateConsistencyCheck:
        """整合性を検証
        
        Args:
            session_state: セッション状態
            item_states: アイテムID -> 状態のマップ
            
        Returns:
            StateConsistencyCheck: 検証結果
        """
        issues = []
        recommendations = []
        
        # アイテムが存在しない場合
        if not item_states:
            if session_state not in {SessionState.PENDING, SessionState.READY}:
                issues.append(
                    f"アイテムが存在しないのにセッション状態が {session_state.value}"
                )
                recommendations.append("セッション状態をPENDINGまたはREADYに戻す")
        
        # セッション状態とアイテム状態の整合性
        if session_state == SessionState.IMPORTED:
            # 完了状態なのに未完了のアイテムがある
            non_terminal = [
                item_id for item_id, state in item_states.items()
                if not state.is_terminal()
            ]
            if non_terminal:
                issues.append(
                    f"セッションIMPORTED状態なのに未完了アイテムあり: {non_terminal}"
                )
                recommendations.append("未完了アイテムを処理するか、セッション状態を戻す")
        
        elif session_state.is_processing():
            # 処理中なのに全アイテムが終了状態
            all_terminal = all(state.is_terminal() for state in item_states.values())
            if all_terminal and item_states:
                issues.append(
                    f"セッション{session_state.value}状態なのに全アイテム終了済み"
                )
                recommendations.append("セッション状態をIMPORTEDまたはFAILEDに更新")
        
        elif session_state in {SessionState.PENDING, SessionState.READY}:
            # 準備段階なのに処理中のアイテムがある
            processing = [
                item_id for item_id, state in item_states.items()
                if state.is_processing()
            ]
            if processing:
                issues.append(
                    f"セッション{session_state.value}状態なのに処理中アイテムあり: {processing}"
                )
                recommendations.append("セッション状態をPROCESSINGに更新")
        
        # 成功率のチェック
        if item_states:
            success_count = sum(1 for state in item_states.values() if state.is_success())
            total_count = len(item_states)
            success_rate = success_count / total_count
            
            if session_state == SessionState.FAILED and success_rate > 0.5:
                issues.append(
                    f"セッションFAILED状態だが成功率{success_rate:.1%}と高い"
                )
                recommendations.append("セッション状態をIMPORTEDに変更を検討")
            
            elif session_state == SessionState.IMPORTED and success_rate < 0.5:
                issues.append(
                    f"セッションIMPORTED状態だが成功率{success_rate:.1%}と低い"
                )
                recommendations.append("セッション状態をFAILEDに変更を検討")
        
        return StateConsistencyCheck(
            is_consistent=len(issues) == 0,
            session_state=session_state,
            item_states=item_states,
            issues=issues,
            recommendations=recommendations,
        )
