"""Local Import監査ログリポジトリ

監査ログをDBテーブルに保存・取得します。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, BigInteger, Text, desc, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from core.db import db
from bounded_contexts.photonest.infrastructure.local_import.audit_logger import (
    AuditLogEntry,
    LogCategory,
    LogLevel,
)

BigInt = BigInteger().with_variant(db.Integer, "sqlite")


class LocalImportAuditLog(db.Model):
    """Local Import監査ログテーブル
    
    すべての状態遷移、エラー、パフォーマンスを記録します。
    """
    
    __tablename__ = "local_import_audit_log"
    
    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    
    # 基本情報
    timestamp: Mapped[datetime] = mapped_column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    level: Mapped[str] = mapped_column(
        db.Enum(
            "debug",
            "info",
            "warning",
            "error",
            "critical",
            name="audit_log_level",
        ),
        nullable=False,
        default="info",
        index=True,
    )
    category: Mapped[str] = mapped_column(
        db.Enum(
            "state_transition",
            "file_operation",
            "db_operation",
            "validation",
            "duplicate_check",
            "error",
            "performance",
            "consistency",
            name="audit_log_category",
        ),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # コンテキスト
    session_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        db.ForeignKey("picker_session.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    item_id: Mapped[Optional[str]] = mapped_column(db.String(255), nullable=True, index=True)
    request_id: Mapped[Optional[str]] = mapped_column(db.String(255), nullable=True, index=True)
    task_id: Mapped[Optional[str]] = mapped_column(db.String(255), nullable=True, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(db.String(255), nullable=True)
    
    # 詳細データ（JSON）
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # エラー情報
    error_type: Mapped[Optional[str]] = mapped_column(db.String(255), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # 推奨アクション（JSON配列）
    recommended_actions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    
    # パフォーマンス情報
    duration_ms: Mapped[Optional[float]] = mapped_column(db.Float, nullable=True)
    
    # 状態遷移情報
    from_state: Mapped[Optional[str]] = mapped_column(db.String(50), nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(db.String(50), nullable=True)
    
    # インデックス
    __table_args__ = (
        db.Index("idx_session_timestamp", "session_id", "timestamp"),
        db.Index("idx_item_timestamp", "item_id", "timestamp"),
        db.Index("idx_level_category", "level", "category"),
    )
    
    @classmethod
    def from_audit_entry(cls, entry: AuditLogEntry) -> LocalImportAuditLog:
        """AuditLogEntryからモデルを作成"""
        return cls(
            timestamp=entry.timestamp,
            level=entry.level.value,
            category=entry.category.value,
            message=entry.message,
            session_id=entry.session_id,
            item_id=entry.item_id,
            request_id=entry.request_id,
            task_id=entry.task_id,
            user_id=entry.user_id,
            details=entry.details,
            error_type=entry.error_type,
            error_message=entry.error_message,
            stack_trace=entry.stack_trace,
            recommended_actions=entry.recommended_actions,
            duration_ms=entry.duration_ms,
            from_state=getattr(entry, "from_state", None),
            to_state=getattr(entry, "to_state", None),
        )
    
    def to_dict(self) -> dict:
        """辞書に変換"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "level": self.level,
            "category": self.category,
            "message": self.message,
            "session_id": self.session_id,
            "item_id": self.item_id,
            "details": self.details,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "recommended_actions": self.recommended_actions,
            "duration_ms": self.duration_ms,
            "from_state": self.from_state,
            "to_state": self.to_state,
        }


class AuditLogRepository:
    """監査ログリポジトリ"""
    
    def __init__(self, session: Session):
        self._session = session
    
    def save(self, entry: AuditLogEntry) -> LocalImportAuditLog:
        """ログエントリを保存
        
        Args:
            entry: 監査ログエントリ
            
        Returns:
            LocalImportAuditLog: 保存されたモデル
        """
        log = LocalImportAuditLog.from_audit_entry(entry)
        self._session.add(log)
        self._session.flush()
        return log
    
    def get_by_session(
        self,
        session_id: int,
        limit: int = 100,
        level: Optional[LogLevel] = None,
        category: Optional[LogCategory] = None,
    ) -> list[LocalImportAuditLog]:
        """セッションに関連するログを取得
        
        Args:
            session_id: セッションID
            limit: 取得件数上限
            level: ログレベルフィルタ
            category: カテゴリフィルタ
            
        Returns:
            list[LocalImportAuditLog]: ログのリスト
        """
        query = select(LocalImportAuditLog).where(
            LocalImportAuditLog.session_id == session_id
        )
        
        if level:
            query = query.where(LocalImportAuditLog.level == level.value)
        
        if category:
            query = query.where(LocalImportAuditLog.category == category.value)
        
        query = query.order_by(desc(LocalImportAuditLog.timestamp)).limit(limit)
        
        return list(self._session.execute(query).scalars())
    
    def get_by_item(
        self,
        item_id: str,
        limit: int = 50,
    ) -> list[LocalImportAuditLog]:
        """アイテムに関連するログを取得
        
        Args:
            item_id: アイテムID
            limit: 取得件数上限
            
        Returns:
            list[LocalImportAuditLog]: ログのリスト
        """
        query = (
            select(LocalImportAuditLog)
            .where(LocalImportAuditLog.item_id == item_id)
            .order_by(desc(LocalImportAuditLog.timestamp))
            .limit(limit)
        )
        
        return list(self._session.execute(query).scalars())
    
    def get_errors(
        self,
        session_id: Optional[int] = None,
        limit: int = 50,
    ) -> list[LocalImportAuditLog]:
        """エラーログを取得
        
        Args:
            session_id: セッションID（オプション）
            limit: 取得件数上限
            
        Returns:
            list[LocalImportAuditLog]: エラーログのリスト
        """
        query = select(LocalImportAuditLog).where(
            LocalImportAuditLog.level.in_(["error", "critical"])
        )
        
        if session_id is not None:
            query = query.where(LocalImportAuditLog.session_id == session_id)
        
        query = query.order_by(desc(LocalImportAuditLog.timestamp)).limit(limit)
        
        return list(self._session.execute(query).scalars())
    
    def get_state_transitions(
        self,
        session_id: int,
    ) -> list[LocalImportAuditLog]:
        """状態遷移履歴を取得
        
        Args:
            session_id: セッションID
            
        Returns:
            list[LocalImportAuditLog]: 状態遷移ログのリスト
        """
        query = (
            select(LocalImportAuditLog)
            .where(
                LocalImportAuditLog.session_id == session_id,
                LocalImportAuditLog.category == "state_transition",
            )
            .order_by(LocalImportAuditLog.timestamp)
        )
        
        return list(self._session.execute(query).scalars())
    
    def get_performance_metrics(
        self,
        session_id: int,
    ) -> list[LocalImportAuditLog]:
        """パフォーマンスメトリクスを取得
        
        Args:
            session_id: セッションID
            
        Returns:
            list[LocalImportAuditLog]: パフォーマンスログのリスト
        """
        query = (
            select(LocalImportAuditLog)
            .where(
                LocalImportAuditLog.session_id == session_id,
                LocalImportAuditLog.category == "performance",
            )
            .order_by(LocalImportAuditLog.timestamp)
        )
        
        return list(self._session.execute(query).scalars())
    
    def cleanup_old_logs(self, days: int = 30) -> int:
        """古いログを削除
        
        Args:
            days: 保持日数
            
        Returns:
            int: 削除件数
        """
        cutoff = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        cutoff = cutoff.replace(day=cutoff.day - days)
        
        result = self._session.execute(
            db.delete(LocalImportAuditLog).where(
                LocalImportAuditLog.timestamp < cutoff
            )
        )
        
        return result.rowcount
